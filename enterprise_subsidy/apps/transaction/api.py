"""
Core business logic around transactions.
"""
import logging
from datetime import datetime
from typing import Optional

import requests
from django.utils import timezone
from openedx_ledger.api import reverse_full_transaction
from openedx_ledger.models import TransactionStateChoices

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.core.event_bus import send_transaction_reversed_event
from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler
from enterprise_subsidy.apps.transaction.utils import generate_transaction_reversal_idempotency_key

from .exceptions import TransactionFulfillmentCancelationException

logger = logging.getLogger(__name__)


def cancel_transaction_fulfillment(transaction):
    """
    Cancels the edx-platform fulfillment (typically the verified enrollment gets moved
    to the ``audit`` mode).
    """
    if transaction.state != TransactionStateChoices.COMMITTED:
        logger.error(
            "[fulfillment cancelation] %s is not committed, will not cancel fulfillment",
            transaction.uuid,
        )
        raise TransactionFulfillmentCancelationException(
            "Transaction is not committed"
        )
    if not transaction.fulfillment_identifier:
        logger.error(
            "[fulfillment cancelation] %s has no fulfillment uuid, will not cancel fulfillment",
            transaction.uuid,
        )
        raise TransactionFulfillmentCancelationException(
            "Transaction has no associated platform fulfillment identifier"
        )

    try:
        EnterpriseApiClient().cancel_fulfillment(transaction.fulfillment_identifier)
    except requests.exceptions.HTTPError as exc:
        error_msg = (
            "Error canceling platform fulfillment "
            f"{transaction.fulfillment_identifier}: {exc}"
        )
        logger.exception("[fulfillment cancelation] %s", error_msg)
        raise TransactionFulfillmentCancelationException(error_msg) from exc


def cancel_transaction_external_fulfillment(transaction) -> None:
    """
    Cancels all related external fulfillments for the given transaction.

    Note: All related external fulfillments that do NOT refer to a GEAG allocation _are skipped_, as only GEAG external
    fulfillments are currently supported. A warning will be logged.

    Returns: None

    Raises:
        TransactionFulfillmentCancelationException:
            Either when:
                1. The transaction is not committed.
                2. The transaction was committed and there are external fulfillments, but
                   none of the external fulfillment providers were understood.
        requests.exceptions.HTTPError:
            Calling the external platform API to cancel an external fulfillment failed for at least one external
            reference related to the given transaction.

    """
    if transaction.state != TransactionStateChoices.COMMITTED:
        logger.info(
            "[fulfillment cancelation] %s is not committed, will not cancel fulfillment",
            transaction.uuid,
        )
        raise TransactionFulfillmentCancelationException(
            "Transaction is not committed"
        )

    references = list(transaction.external_reference.all())
    if not references:
        return

    fulfillment_cancelation_successful = False
    for external_reference in references:
        provider_slug = external_reference.external_fulfillment_provider.slug
        geag_handler = GEAGFulfillmentHandler()
        if provider_slug == geag_handler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG:
            geag_handler.cancel_fulfillment(external_reference)
            fulfillment_cancelation_successful = True
        else:
            logger.warning(
                "[cancel_transaction_external_fulfillment] Don't know how to cancel transaction %s with provider %s",
                transaction.uuid,
                provider_slug,
            )

    if not fulfillment_cancelation_successful:
        raise TransactionFulfillmentCancelationException(
            "External fulfillments exist, but none were successfully canceled."
        )


def reverse_transaction(transaction, unenroll_time: Optional[datetime] = None):
    """
    Creates a reversal for the provided transaction.
    """
    idempotency_key = generate_transaction_reversal_idempotency_key(
        transaction.fulfillment_identifier,
        unenroll_time or timezone.now(),
    )
    reversal = reverse_full_transaction(
        transaction=transaction,
        idempotency_key=idempotency_key,
    )
    transaction.refresh_from_db()
    send_transaction_reversed_event(transaction)
    return reversal
