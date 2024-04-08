"""
Core business logic around transactions.
"""
import logging

import requests
from django.utils import timezone
from openedx_ledger.api import reverse_full_transaction
from openedx_ledger.models import TransactionStateChoices

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
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
        logger.info(
            "[fulfillment cancelation] %s is not committed, will not cancel fulfillment",
            transaction.uuid,
        )
        raise TransactionFulfillmentCancelationException(
            "Transaction is not committed"
        )
    if not transaction.fulfillment_identifier:
        logger.info(
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


def cancel_transaction_external_fulfillment(transaction):
    """
    Cancels all related external GEAG allocations for the given transaction.

    raises:
      FulfillmentException if the related external references for the transaction
        are not for a GEAG fulfillment provider.
    """
    if transaction.state != TransactionStateChoices.COMMITTED:
        logger.info(
            "[fulfillment cancelation] %s is not committed, will not cancel fulfillment",
            transaction.uuid,
        )
        raise TransactionFulfillmentCancelationException(
            "Transaction is not committed"
        )

    for external_reference in transaction.external_reference.all():
        provider_slug = external_reference.external_fulfillment_provider.slug
        geag_handler = GEAGFulfillmentHandler()
        if provider_slug == geag_handler.EXTERNAL_FULFILLMENT_PROVIDER_SLUG:
            geag_handler.cancel_fulfillment(external_reference)
        else:
            logger.warning(
                '[fulfillment cancelation] dont know how to cancel transaction %s with provider %s',
                transaction.uuid,
                provider_slug,
            )


def reverse_transaction(transaction, unenroll_time=None):
    """
    Creates a reversal for the provided transaction.
    """
    idempotency_key = generate_transaction_reversal_idempotency_key(
        transaction.fulfillment_identifier,
        unenroll_time or timezone.now(),
    )
    return reverse_full_transaction(
        transaction=transaction,
        idempotency_key=idempotency_key,
    )
