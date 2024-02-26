"""
Management command to backpopulate transaction parent_content_key
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
    Management command for backpopulating transaction parent_content_key

    ./manage.py backpopulate_transaction_parent_content_key
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
        Given a transaction (and it's subsidy), backpopulate the parent_content_key.
        """
        logger.info(f"Processing subsidy={subsidy.uuid}, transaction={txn.uuid}")

        try:
            if txn.parent_content_key is None and txn.content_key is not None:
                parent_content_key = subsidy.metadata_summary_for_content(txn.content_key).get('content_key')
                txn.parent_content_key = parent_content_key
                logger.info(
                    f"Found parent_content_key={parent_content_key} "
                    f"for subsidy={subsidy.uuid}, transaction={txn.uuid}"
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception(
                f"Error while processing parent_content_key for subsidy={subsidy.uuid}, transaction={txn.uuid}: {e}"
            )

        if not self.dry_run:
            txn.save()
            logger.info(f"Updated subsidy={subsidy.uuid}, transaction={txn.uuid}")

    def handle(self, *args, **options):
        """
        Find all transactions that are missing parent_content_key and backpopulate them.
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
                # We can only populate the parent_content_key when there's a child content key. Empty child content keys
                # mayhappen with test data.
                incomplete_parent_content_key = Q(parent_content_key__isnull=True) & Q(content_key__isnull=False)
                txn_filter = subsidy_filter & incomplete_parent_content_key

                for txns in batch_by_pk(Transaction, extra_filter=txn_filter):
                    for txn in txns:
                        self.process_transaction(subsidy, txn)
