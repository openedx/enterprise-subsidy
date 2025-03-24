"""
Management command to fetch enterprise enrollment objects that have been unenrolled within the last 24 hours and write
Transaction Reversals where appropriate.
"""
import logging

from django.contrib import auth
from django.core.management.base import BaseCommand
from openedx_ledger.models import Transaction, TransactionStateChoices

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.transaction.api import cancel_transaction_external_fulfillment, reverse_transaction
from enterprise_subsidy.apps.transaction.utils import unenrollment_can_be_refunded

logger = logging.getLogger(__name__)
User = auth.get_user_model()


class Command(BaseCommand):
    """
    Management command for writing Transaction Reversals from recent Enterprise unenrollments data.

    ./manage.py write_reversals_from_enterprise_unenrollments
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dry_run_prefix = ""
        self.dry_run = False
        self.fetched_content_metadata = {}

    def add_arguments(self, parser):
        """
        Entry point for subclassed commands to add custom arguments.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help=(
                'If set, no updates or creates will occur; will instead iterate over '
                'the unenrollments and log the actions that would have been taken.'
            ),
        )

    def handle_reversing_enterprise_course_unenrollment(self, unenrollment):
        """
        Helper method to determine refund eligibility of unenrollments and generating reversals for enterprise course
        fulfillments.

        Returns 0 if no reversal was written, 1 if a reversal was written.
        """
        fulfillment_uuid = unenrollment.get("uuid")
        enterprise_course_enrollment = unenrollment.get("enterprise_course_enrollment")
        enrollment_course_run_key = enterprise_course_enrollment.get("course_id")
        enrollment_unenrolled_at = enterprise_course_enrollment.get("unenrolled_at")

        # Look for a transaction related to the unenrollment
        related_transaction = Transaction.objects.filter(
            uuid=unenrollment.get('transaction_id')
        ).first()
        if not related_transaction:
            logger.info(
                f"{self.dry_run_prefix}No Subsidy Transaction found for enterprise fulfillment: {fulfillment_uuid}"
            )
            return 0
        # Fail early if the transaction is not committed, even though reverse_full_transaction()
        # would throw an exception later anyway.
        if related_transaction.state != TransactionStateChoices.COMMITTED:
            logger.info(
                f"{self.dry_run_prefix}Transaction: {related_transaction} is not in a committed state. "
                f"Skipping Reversal creation."
            )
            return 0

        # Look for a Reversal related to the unenrollment
        existing_reversal = related_transaction.get_reversal()
        if existing_reversal:
            logger.info(
                f"{self.dry_run_prefix}Found existing Reversal: {existing_reversal} for enterprise fulfillment: "
                f"{fulfillment_uuid}. Skipping Reversal creation for Transaction: {related_transaction}."
            )
            return 0

        # Continue on if no reversal found
        logger.info(
            f"{self.dry_run_prefix}No existing Reversal found for enterprise fulfillment: {fulfillment_uuid}. "
            f"Writing Reversal for Transaction: {related_transaction}."
        )

        # Memoize the content metadata for the course run fetched from the enterprise catalog
        if not self.fetched_content_metadata.get(enrollment_course_run_key):
            content_metadata = ContentMetadataApi.get_content_metadata(
                enrollment_course_run_key,
            )
            self.fetched_content_metadata[enrollment_course_run_key] = content_metadata
        else:
            content_metadata = self.fetched_content_metadata.get(enrollment_course_run_key)

        # Check if the OCM unenrollment is refundable
        if not unenrollment_can_be_refunded(
            content_metadata, enterprise_course_enrollment, related_transaction,
        ):
            logger.info(
                f"{self.dry_run_prefix}Unenrollment from course: {enrollment_course_run_key} by user: "
                f"{enterprise_course_enrollment.get('enterprise_customer_user')} is not refundable. "
                f"Related transaction {related_transaction.uuid}."
            )
            return 0

        logger.info(
            f"{self.dry_run_prefix}Course run: {enrollment_course_run_key} is refundable for enterprise "
            f"customer user: {enterprise_course_enrollment.get('enterprise_customer_user')}. Writing "
            f"Reversal record for related transaction {related_transaction.uuid}."
        )

        if not self.dry_run:
            successfully_canceled = cancel_transaction_external_fulfillment(related_transaction)
            if successfully_canceled:
                reverse_transaction(related_transaction, unenroll_time=enrollment_unenrolled_at)
                return 1
            else:
                logger.warning(
                    'Could not cancel external fulfillment for transaction %s, no reversal written',
                    related_transaction.uuid,
                )
                return 0
        else:
            logger.info(
                f"{self.dry_run_prefix}Would have written Reversal record for enterprise fulfillment: "
                f"{fulfillment_uuid}. Transaction: {related_transaction}."
            )
            return 0

    def handle(self, *args, **options):
        """
        Fetch enterprise enrollment objects that have been unenrolled within the last 24 hours and write Transaction
        Reversals where appropriate for each unenrollment.
        """
        if options.get('dry_run'):
            self.dry_run = True
            self.dry_run_prefix = "DRY RUN: "
            logger.info("Running in dry-run mode. No updates or creates will occur.")

        logger.info(
            f"{self.dry_run_prefix}Updating and writing Transaction Reversals from recent Enterprise unenrollments "
            "data"
        )
        recent_unenrollments = EnterpriseApiClient().fetch_recent_unenrollments()
        logger.info(
            f"{self.dry_run_prefix}Found {len(recent_unenrollments)} recent Enterprise unenrollments"
        )

        reversals_processed = 0
        for unenrollment in recent_unenrollments:
            reversals_processed += self.handle_reversing_enterprise_course_unenrollment(unenrollment)

        logger.info(
            f"{self.dry_run_prefix}Completed writing {reversals_processed} Transaction Reversals from recent "
            "Enterprise unenrollments"
        )
