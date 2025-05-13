"""
Subsidy Service signals handler.

The following two scenarios detail what happens when either ECS or a learner initiates unenrollment, and explains how
infinite loops are terminated.

1. When ECS invokes transaction reversal:
=========================================
* Reversal gets created.
  ↳ Emit TRANSACTION_REVERSED signal.
* TRANSACTION_REVERSED triggers the `listen_for_transaction_reversal()` handler.
  ↳ Revoke internal & external fulfillments.
    ↳ Emit LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED openedx event.
  ↳ Emit LEDGER_TRANSACTION_REVERSED openedx event.
* LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED triggers the `handle_lc_enrollment_revoked()` handler.
  ↳ Fail first base case (reversal already exists) and quit. <-------THIS TERMINATES THE INFINITE LOOP!
* LEDGER_TRANSACTION_REVERSED triggers the `update_assignment_status_for_reversed_transaction()` handler.
  ↳ Updates any assignments as needed.

2. When a learner invokes unenrollment:
=======================================
* Enterprise app will perform internal fulfillment revocation.
  ↳ Emit LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED openedx event.
* LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED triggers the `handle_lc_enrollment_revoked()` handler.
  ↳ Revoke external fulfillments.
  ↳ Create reversal.
    ↳ Emit TRANSACTION_REVERSED signal.
* TRANSACTION_REVERSED triggers the `listen_for_transaction_reversal()` handler.
  ↳ Attempt to idempotently revoke external enrollment (API no-op).
  ↳ Attempt to idempotently revoke internal enrollment (API no-op). <---THIS TERMINATES THE INFINITE LOOP!
  ↳ Emit LEDGER_TRANSACTION_REVERSED openedx event.
* LEDGER_TRANSACTION_REVERSED triggers the `update_assignment_status_for_reversed_transaction()` handler.
  ↳ Updates any assignments as needed.
"""
import logging
from uuid import UUID

import dateutil.parser
import requests
from django.conf import settings
from django.dispatch import receiver
from openedx_events.enterprise.signals import LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED
from openedx_ledger.models import Transaction, TransactionStateChoices
from openedx_ledger.signals.signals import TRANSACTION_REVERSED

from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.core.event_bus import send_transaction_reversed_event
from enterprise_subsidy.apps.transaction.api import (
    cancel_transaction_external_fulfillment,
    cancel_transaction_fulfillment,
    reverse_transaction
)
from enterprise_subsidy.apps.transaction.exceptions import TransactionFulfillmentCancelationException
from enterprise_subsidy.apps.transaction.utils import unenrollment_can_be_refunded

logger = logging.getLogger(__name__)


@receiver(TRANSACTION_REVERSED)
def listen_for_transaction_reversal(sender, **kwargs):
    """
    Listen for the TRANSACTION_REVERSED signals and issue an unenrollment request to internal and external fulfillments.

    This subsequently emits a LEDGER_TRANSACTION_REVERSED openedx event to signal to enterprise-access that any
    assignents need to be reversed too.
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
        cancel_transaction_external_fulfillment(transaction)
        cancel_transaction_fulfillment(transaction)
        send_transaction_reversed_event(transaction)
    except TransactionFulfillmentCancelationException as exc:
        error_msg = f"Error canceling platform fulfillment {transaction.fulfillment_identifier}: {exc}"
        logger.exception(error_msg)
        raise exc


@receiver(LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED)
def handle_lc_enrollment_revoked(**kwargs):
    """
    openedx event handler to respond to LearnerCreditEnterpriseCourseEnrollment revocations.
    """
    if not settings.ENABLE_HANDLE_LC_ENROLLMENT_REVOKED:
        logger.info(
            "Handling of LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED event has been disabled. "
            "Skipping handle_lc_enrollment_revoked() handler."
        )
        return
    revoked_enrollment_data = kwargs.get('learner_credit_course_enrollment')
    shared_handle_lc_enrollment_revoked(
        fulfillment_uuid=revoked_enrollment_data.uuid,
        transaction_uuid=revoked_enrollment_data.transaction_id,
        enterprise_course_enrollment=revoked_enrollment_data.enterprise_course_enrollment.__dict__,
    )


def shared_handle_lc_enrollment_revoked(
    fulfillment_uuid: UUID,
    transaction_uuid: UUID,
    enterprise_course_enrollment: dict,
    dry_run: bool = False
) -> bool:
    """
    Actually handle LearnerCreditEnterpriseCourseEnrollment revocations.

    The critical bits of this handler's business logic can be summarized as follows:

    1. Receive LC fulfillment revocation event and run this handler.
    2. BASE CASE: If this fulfillment's transaction has already been reversed, quit.
    3. Cancel/unenroll any external fulfillments related to the transaction.
    4. BASE CASE: If the refund deadline has passed, quit.
    5. Reverse the transaction.


    Note: This function is reusable by either event handlers being fed attrs-like
    openedx_events.enterprise.data.EnterpriseCourseEnrollment objects, OR management commands being
    fed data from the /enterprise/api/v1/operator/enterprise-subsidy-fulfillment/unenrolled/ API
    endpoint.

    Args:
        learner_credit_course_enrollment (dict):
            Dict-serialized representation of LearnerCreditEnterpriseCourseEnrollment. Callers with
            an attrs object must first call .__dict__ before passing to this function.

    Returns: True if a reversal was written.
    """
    # Normalize to str in case we receive a CourseLocator.
    enrollment_course_run_key = str(enterprise_course_enrollment.get("course_id"))
    enrollment_unenrolled_at = enterprise_course_enrollment.get("unenrolled_at")
    # Normalize to datetime in case we receive a str.
    if isinstance(enrollment_unenrolled_at, str):
        enrollment_unenrolled_at = dateutil.parser.parse(enrollment_unenrolled_at)

    # Look for a transaction related to the unenrollment
    related_transaction = Transaction.objects.filter(uuid=transaction_uuid).first()
    if not related_transaction:
        logger.info(
            f"No Subsidy Transaction found for enterprise fulfillment: {fulfillment_uuid}"
        )
        return False
    # Fail early if the transaction is not committed, even though reverse_full_transaction()
    # would throw an exception later anyway.
    if related_transaction.state != TransactionStateChoices.COMMITTED:
        logger.info(
            f"Transaction: {related_transaction} is not in a committed state. "
            f"Skipping Reversal creation."
        )
        return False

    # Look for a Reversal related to the unenrollment
    existing_reversal = related_transaction.get_reversal()
    if existing_reversal:
        logger.info(
            f"Found existing Reversal: {existing_reversal} for enterprise fulfillment: "
            f"{fulfillment_uuid}. Skipping Reversal creation for Transaction: {related_transaction}."
        )
        return False

    # Continue on if no reversal found
    logger.info(
        f"No existing Reversal found for enterprise fulfillment: {fulfillment_uuid}. "
        f"Proceeding to attempt to write Reversal for Transaction: {related_transaction}."
    )

    if not dry_run:
        # Opportunitstically cancel any external fulfillments. [ENT-10284] Do this BEFORE checking
        # refundability in order to prioritize complete unenrollment and system integrity even in
        # non-refundable situations.
        try:
            cancel_transaction_external_fulfillment(related_transaction)
        except (TransactionFulfillmentCancelationException, requests.exceptions.HTTPError) as exc:
            # If any external fulfillments were not canceled, we should not write a reversal because
            # content would continue to be accessible without payment.
            logger.error(
                (
                    '[shared_handle_lc_enrollment_revoked] Failed attempting to cancel external fulfillment(s) '
                    'for transaction %s, so no reversal written. Swallowed exception: %s'
                ),
                related_transaction.uuid,
                exc,
            )
            return False
    else:
        logger.info(
            f"[DRY_RUN] Would have attempted cancelling external fulfillments for enterprise fulfillment: "
            f"{fulfillment_uuid}. Transaction: {related_transaction}."
        )

    # NOTE: get_content_metadata() is backed by TieredCache, so this would be performant if a bunch learners unenroll
    # from the same course at the same time. However, normally no two learners in the same course would unenroll within
    # a single cache timeout period, so we'd expect this to normally always re-fetch from remote API. That's OK because
    # unenrollment volumes are manageable.
    content_metadata = ContentMetadataApi.get_content_metadata(
        enrollment_course_run_key,
    )

    # Check if the OCM unenrollment is refundable
    if not unenrollment_can_be_refunded(
        content_metadata, enterprise_course_enrollment, related_transaction,
    ):
        logger.info(
            f"[REVOCATION_NOT_REFUNDABLE] Unenrollment from course: {enrollment_course_run_key} by user: "
            f"{enterprise_course_enrollment.get('enterprise_customer_user')} is not refundable. "
            f"Transaction uuid: {related_transaction.uuid}"
        )
        return False

    if not dry_run:
        reverse_transaction(related_transaction, unenroll_time=enrollment_unenrolled_at)
        logger.info(
            f"[REVOCATION_SUCCESSFULLY_REVERSED] Course run: {enrollment_course_run_key} is refundable for enterprise "
            f"customer user: {enterprise_course_enrollment.get('enterprise_customer_user')}. "
            f"Reversal record for transaction uuid {related_transaction.uuid} has been created."
        )
    else:
        logger.info(
            f"[DRY_RUN] Would have written Reversal record for enterprise fulfillment: "
            f"{fulfillment_uuid}. Transaction: {related_transaction}."
        )
    return True
