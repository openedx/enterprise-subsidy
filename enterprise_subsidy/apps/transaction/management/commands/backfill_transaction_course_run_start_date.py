import logging
from django.core.management.base import BaseCommand
from openedx_ledger.models import Transaction
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.subsidy.models import Subsidy
from dateutil import parser

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Backfill course_run_start_date for Transactions by fetching from content metadata."

    def handle(self, *args, **options):
        content_api = ContentMetadataApi()
        transactions = Transaction.objects.filter(course_run_start_date__isnull=True, content_key__isnull=False).exclude(content_key='')
        logger.info(f"Starting backfill for {transactions.count()} transactions")
        updated_count = 0
        error_count = 0
        for transaction in transactions.iterator(chunk_size=100):
            try:
                if transaction.ledger and transaction.ledger.subsidy_set.exists():
                    subsidy = transaction.ledger.subsidy_set.first()
                    enterprise_customer_uuid = subsidy.enterprise_customer_uuid
                    content_summary = content_api.get_content_summary(enterprise_customer_uuid, transaction.content_key)
                    course_run_start_date_str = content_summary.get('course_run_start_date')
                    if course_run_start_date_str:
                        course_run_start_date = parser.parse(course_run_start_date_str)
                        transaction.course_run_start_date = course_run_start_date
                        transaction.save(update_fields=['course_run_start_date'])
                        updated_count += 1
                        if updated_count % 100 == 0:
                            logger.info(f"Updated {updated_count} transactions so far")
            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to backfill course_run_start_date for transaction {transaction.uuid}: {e}")
                continue
        logger.info(f"Backfill completed. Updated: {updated_count}, Errors: {error_count}")
