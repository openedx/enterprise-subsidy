"""
Management command to fetch enterprise enrollment objects that have been unenrolled within the last 24 hours and write
Transaction Reversals where appropriate.
"""
import logging
from uuid import UUID

from django.contrib import auth
from django.core.management.base import BaseCommand

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.transaction.signals.handlers import shared_handle_lc_enrollment_revoked

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

    def handle_lc_enrollment_revoked(self, unenrollment) -> int:
        """
        Helper method to determine refund eligibility of unenrollments and generating reversals for enterprise course
        fulfillments.

        Returns 0 if no reversal was written, 1 if a reversal was written.
        """
        reversal_written = shared_handle_lc_enrollment_revoked(
            fulfillment_uuid=UUID(unenrollment.get("uuid")),
            transaction_uuid=UUID(unenrollment.get("transaction_id")),
            enterprise_course_enrollment=unenrollment.get("enterprise_course_enrollment"),
            dry_run=self.dry_run,
        )
        return 1 if reversal_written else 0

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
            reversals_processed += self.handle_lc_enrollment_revoked(unenrollment)

        logger.info(
            f"{self.dry_run_prefix}Completed writing {reversals_processed} Transaction Reversals from recent "
            "Enterprise unenrollments"
        )
