"""
Management command to backpopulate transaction email and title
"""
import logging

from django.core.management.base import BaseCommand
from django.db.models import Q
from openedx_ledger.models import Transaction

from enterprise_subsidy.apps.subsidy.models import Subsidy
from enterprise_subsidy.apps.transaction.utils import batch_by_pk

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for backpopulating transaction email and title

    ./manage.py backpopulate_transaction_email_and_title
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dry_run = False
        self.include_internal_subsidies = False

    def add_arguments(self, parser):
        """
        Entry point for subclassed commands to add custom arguments.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help=(
                'If set, no updates will occur; will instead log '
                'the actions that would have been taken.'
            ),
        )
        parser.add_argument(
            '--include-internal-subsidies',
            action='store_true',
            dest='include_internal_subsidies',
            help=(
                'If set, internal subsidies will be included in the backpopulating'
            ),
        )

    def process_transaction(self, subsidy, txn):
        """
        Given a transaction (and it's subsidy), backpopulate the email and title
        """
        logger.info(f"Processing {subsidy.uuid} transaction {txn.uuid}")

        if txn.lms_user_email is None:
            lms_user_email = subsidy.email_for_learner(txn.lms_user_id)
            txn.lms_user_email = lms_user_email
            logger.info(f"Found {lms_user_email} for {subsidy.uuid} transaction {txn.uuid}")
        if txn.content_title is None:
            content_title = subsidy.title_for_content(txn.content_key)
            txn.content_title = content_title
            logger.info(f"Found {content_title} for {subsidy.uuid} transaction {txn.uuid}")

        if not self.dry_run:
            txn.save()
            logger.info(f"Updated {subsidy.uuid} transaction {txn.uuid}")

    def handle(self, *args, **options):
        """
        Find all transactions that are missing email or title and backpopulate them
        """
        if options.get('dry_run'):
            self.dry_run = True
            logger.info("Running in dry-run mode. No updates will occur.")

        if options.get('include_internal_subsidies'):
            self.include_internal_subsidies = True
            logger.info("Including internal_only subsidies while backpopulating.")

        subsidy_filter = Q()
        if not self.include_internal_subsidies:
            subsidy_filter = Q(internal_only=False)

        for subsidies in batch_by_pk(Subsidy, extra_filter=subsidy_filter):
            for subsidy in subsidies:
                logger.info(f"Processing subsidy {subsidy.uuid}")
                subsidy_filter = Q(ledger=subsidy.ledger)
                incomplete_only_filter = Q(lms_user_email__isnull=True) | Q(content_title__isnull=True)
                txn_filter = subsidy_filter & incomplete_only_filter
                for txns in batch_by_pk(Transaction, extra_filter=txn_filter):
                    for txn in txns:
                        self.process_transaction(subsidy, txn)
