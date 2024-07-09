"""
Management command to replay openedx transaction reversal events for all
currently-reversed ledger transactions.
"""
import logging

from django.core.management.base import BaseCommand
from openedx_events.event_bus import get_producer
from openedx_ledger.models import Transaction, TransactionStateChoices

from enterprise_subsidy.apps.core.event_bus import send_transaction_reversed_event

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Management command for writing Transaction Reversals from recent Enterprise unenrollments data.

    ./manage.py write_reversals_from_enterprise_unenrollments
    """

    def add_arguments(self, parser):
        """
        Entry point for subclassed commands to add custom arguments.
        """
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help=(
                'If set, will only log a message about what events we would have produced,'
                'without actually producing them.'
            ),
        )

    def handle(self, *args, **options):
        """
        Finds all reversed transactions and emits a reversal event for each.
        """
        all_reversed_transactions = Transaction.objects.select_related('reversal').filter(
            state=TransactionStateChoices.COMMITTED,
            reversal__isnull=False,
            reversal__state=TransactionStateChoices.COMMITTED,
        )

        for transaction_record in all_reversed_transactions:
            if not options.get('dry_run'):
                send_transaction_reversed_event(transaction_record)
                logger.info(f'Sent reversal event for transaction {transaction_record.uuid}')
            else:
                logger.info(f'[DRY RUN] Would have sent reversal event for transaction {transaction_record.uuid}')

        if not options.get('dry_run'):
            # Retrieve the cached producer and tell it to prepare for shutdown before this command exits.
            # This ensures that all messages in the send queue are flushed. Without this, this command
            # will exit and drop all produced messages before they can be sent to the broker.
            # See: https://github.com/openedx/event-bus-kafka/blob/main/edx_event_bus_kafka/internal/producer.py#L324
            # and https://github.com/openedx/event-bus-kafka/blob/main/docs/decisions/0007-producer-polling.rst
            get_producer().prepare_for_shutdown()
