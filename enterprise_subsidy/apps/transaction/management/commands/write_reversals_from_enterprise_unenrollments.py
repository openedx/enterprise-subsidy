"""
Management command to fetch enterprise enrollment objects that have been unenrolled within the last 24 hours and write
Transaction Reversals where appropriate.
"""
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import auth
from django.core.management.base import BaseCommand
from getsmarter_api_clients.geag import GetSmarterEnterpriseApiClient
from openedx_ledger.models import Transaction, TransactionStateChoices

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.transaction.api import cancel_transaction_external_fulfillment, reverse_transaction

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
        self.geag_client = GetSmarterEnterpriseApiClient(
            client_id=settings.GET_SMARTER_OAUTH2_KEY,
            client_secret=settings.GET_SMARTER_OAUTH2_SECRET,
            provider_url=settings.GET_SMARTER_OAUTH2_PROVIDER_URL,
            api_url=settings.GET_SMARTER_API_URL
        )
        self.automatic_external_cancellation = getattr(
            settings,
            "ENTERPRISE_SUBSIDY_AUTOMATIC_EXTERNAL_CANCELLATION",
            False
        )

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

    def convert_unenrollment_datetime_string(self, datetime_str):
        """
        Helper method to strip microseconds from a datetime object
        """
        try:
            formatted_datetime = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            formatted_datetime = datetime.strptime(datetime_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        return formatted_datetime

    def unenrollment_can_be_refunded(
        self,
        content_metadata,
        enterprise_course_enrollment,
    ):
        """
        helper method to determine if an unenrollment is refundable
        """
        # Retrieve the course start date from the content metadata
        enrollment_course_run_key = enterprise_course_enrollment.get("course_id")
        enrollment_created_at = enterprise_course_enrollment.get("created")
        course_start_date = None
        if content_metadata.get('content_type') == 'courserun':
            course_start_date = content_metadata.get('start')
        else:
            for run in content_metadata.get('course_runs', []):
                if run.get('key') == enrollment_course_run_key:
                    course_start_date = run.get('start')
                    break

        if not course_start_date:
            logger.warning(
                f"No course start date found for course run: {enrollment_course_run_key}. "
                "Unable to determine refundability."
            )
            return False

        # https://2u-internal.atlassian.net/browse/ENT-6825
        # OCM course refundability is defined as True IFF:
        # ie MAX(enterprise enrollment created at, course start date) + 14 days > unenrolled_at date
        enrollment_created_at = enterprise_course_enrollment.get("created")
        enrollment_unenrolled_at = enterprise_course_enrollment.get("unenrolled_at")

        enrollment_created_datetime = self.convert_unenrollment_datetime_string(enrollment_created_at)
        course_start_datetime = self.convert_unenrollment_datetime_string(course_start_date)
        enrollment_unenrolled_at_datetime = self.convert_unenrollment_datetime_string(enrollment_unenrolled_at)
        refund_cutoff_date = max(course_start_datetime, enrollment_created_datetime) + timedelta(days=14)

        if refund_cutoff_date > enrollment_unenrolled_at_datetime:
            logger.info(
                f"Course run: {enrollment_course_run_key} is refundable for enterprise customer user: "
                f"{enterprise_course_enrollment.get('enterprise_customer_user')}. Writing Reversal record."
            )
            return True
        else:
            logger.info(
                f"Unenrollment from course: {enrollment_course_run_key} by user: "
                f"{enterprise_course_enrollment.get('enterprise_customer_user')} is not refundable."
            )
            return False

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

        # On initial release we are only supporting learner initiated unenrollments for OCM courses.
        # OCM courses are identified by the lack of an external_reference on the Transaction object.
        # Externally referenced transactions can be unenrolled through the Django admin actions related to the
        # Transaction model.
        if related_transaction.external_reference.exists() and not self.automatic_external_cancellation:
            logger.info(
                f"{self.dry_run_prefix}Found unenrolled enterprise fulfillment: {fulfillment_uuid} related to "
                f"an externally referenced transaction: {related_transaction.external_reference.first()}. "
                f"Skipping ENTERPRISE_SUBSIDY_AUTOMATIC_EXTERNAL_CANCELLATION={self.automatic_external_cancellation}."
            )
            return 0

        # Memoize the content metadata for the course run fetched from the enterprise catalog
        if not self.fetched_content_metadata.get(enrollment_course_run_key):
            content_metadata = ContentMetadataApi.get_content_metadata(
                enrollment_course_run_key,
            )
            self.fetched_content_metadata[enrollment_course_run_key] = content_metadata
        else:
            content_metadata = self.fetched_content_metadata.get(enrollment_course_run_key)

        # Check if the OCM unenrollment is refundable
        if not self.unenrollment_can_be_refunded(content_metadata, enterprise_course_enrollment):
            logger.info(
                f"{self.dry_run_prefix}Unenrollment from course: {enrollment_course_run_key} by user: "
                f"{enterprise_course_enrollment.get('enterprise_customer_user')} is not refundable."
            )
            return 0

        logger.info(
            f"{self.dry_run_prefix}Course run: {enrollment_course_run_key} is refundable for enterprise "
            f"customer user: {enterprise_course_enrollment.get('enterprise_customer_user')}. Writing "
            "Reversal record."
        )

        if not self.dry_run:
            cancel_transaction_external_fulfillment(related_transaction)
            reverse_transaction(related_transaction, unenroll_time=enrollment_unenrolled_at)
            return 1
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
