"""
Subsidy Service signals handler.
"""
import logging

import requests
from django.dispatch import receiver
from openedx_ledger.signals.signals import TRANSACTION_REVERSED

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient

logger = logging.getLogger(__name__)


@receiver(TRANSACTION_REVERSED)
def listen_for_transaction_reversal(sender, **kwargs):
    """
    Listen for the TRANSACTION_REVERSED signals and issue an unenrollment request to platform.
    """
    logger.info(
        f"Received TRANSACTION_REVERSED signal from {sender}, attempting to unenroll platform enrollment object"
    )
    reversal = kwargs.get('reversal')
    transaction = reversal.transaction
    if not transaction.fulfillment_identifier:
        msg = f"transaction: {transaction.uuid} has no platform fulfillment uuid, unable to unenroll"
        logger.info(msg)
        raise ValueError(msg)
    try:
        EnterpriseApiClient().cancel_fulfillment(transaction.fulfillment_identifier)
    except requests.exceptions.HTTPError as exc:
        error_msg = f"Error canceling platform fulfillment {transaction.fulfillment_identifier}: {exc}"
        logger.exception(error_msg)
        raise exc
