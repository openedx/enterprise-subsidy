"""
Subsidy Service signals handler.
"""
import logging

import requests
from django.dispatch import receiver
from openedx_events.enterprise.data import SubsidyRedemption
from openedx_events.enterprise.signals import SUBSIDY_REDEMPTION_REVERSED
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
        subsidy_redemption = SubsidyRedemption(
            subsidy_identifier=transaction.subsidy_access_policy_uuid,
            content_key=transaction.content_key,
            lms_user_id=transaction.lms_user_id
        )
        SUBSIDY_REDEMPTION_REVERSED.send_event(
            redemption=subsidy_redemption,
        )
    except requests.exceptions.HTTPError as exc:
        error_msg = f"Error canceling platform fulfillment {transaction.fulfillment_identifier}: {exc}"
        logger.exception(error_msg)
        raise exc
