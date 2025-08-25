"""
Mnagement command to backpopulate course_run_start_date for Transactions.
"""
import logging

from django.core.management.base import BaseCommand
from openedx_ledger.models import Transaction

from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.transaction.utils import normalize_to_datetime

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command to backpopulate course_run_start_date for Transaction records.

    Iterates through Transaction records with null course_run_start_date and populates
    them by fetching data from the content metadata API.
    """
    help = "Backpopulating course_run_start_date for Transactions by fetching from content metadata."

    def add_arguments(self, parser):
        parser.add_argument(
            '--since',
            type=str,
            help='Only update transactions modified on or after this date (ISO format, e.g. 2025-09-01)',
            required=False,
        )

    def handle(self, *args, **options):
        content_api = ContentMetadataApi()
        transactions = (
            Transaction.objects
            .filter(course_run_start_date__isnull=True, content_key__isnull=False)
            .exclude(content_key='')
        )
        since = options.get('since')
        if since:
            try:
                since_date = normalize_to_datetime(since)
                transactions = transactions.filter(modified__gte=since_date)
                logger.info(f"Filtering transactions modified since {since_date}")
            except (ValueError, TypeError) as e:
                # Handle date parsing errors specifically
                logger.error(f"Invalid date for --since: {since}. Error: {e}")
                return
        logger.info(f"Starting backpopulate for {transactions.count()} transactions")
        updated_count = 0
        error_count = 0
        for transaction in transactions.iterator(chunk_size=100):
            try:
                subsidy = getattr(transaction.ledger, 'subsidy', None)
                if transaction.ledger and subsidy:
                    enterprise_customer_uuid = subsidy.enterprise_customer_uuid
                    content_summary = content_api.get_content_summary(enterprise_customer_uuid, transaction.content_key)
                    course_run_start_date_str = content_summary.get('course_run_start_date')
                    if course_run_start_date_str:
                        course_run_start_date = normalize_to_datetime(course_run_start_date_str)
                        transaction.course_run_start_date = course_run_start_date
                        transaction.save(update_fields=['course_run_start_date'])
                        updated_count += 1
                        if updated_count % 100 == 0:
                            logger.info(f"Updated {updated_count} transactions so far")
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Catch broad exceptions to prevent one bad transaction from stopping the entire process
                error_count += 1
                logger.warning(f"Failed to backfill course_run_start_date for transaction {transaction.uuid}: {e}")
                continue
        logger.info(f"Backfill completed. Updated: {updated_count}, Errors: {error_count}")
