"""
Tests for the migration_utils.py module.
"""
from django.test import TestCase
from openedx_ledger.constants import INITIAL_DEPOSIT_TRANSACTION_SLUG
from openedx_ledger.models import Transaction
from openedx_ledger.test_utils.factories import AdjustmentFactory, DepositFactory, LedgerFactory, TransactionFactory

from enterprise_subsidy.apps.subsidy import migration_utils


class MigrationUtilsTests(TestCase):
    """
    Tests for utils used for migrations.
    """
    def test_find_legacy_initial_transactions(self):
        """
        Test find_legacy_initial_transactions(), used for a data migration to backfill initial deposits.
        """
        ledgers = [
            (LedgerFactory(), False),
            (LedgerFactory(), False),
            (LedgerFactory(), True),
            (LedgerFactory(), False),
            (LedgerFactory(), True),
        ]
        expected_legacy_initial_transactions = []
        for ledger, create_initial_deposit in ledgers:
            # Simulate a legacy initial transaction (i.e. transaction WITHOUT a deposit).
            initial_transaction = TransactionFactory(
                ledger=ledger,
                idempotency_key=INITIAL_DEPOSIT_TRANSACTION_SLUG,
                quantity=100,
            )
            if create_initial_deposit:
                # Make it a modern initial deposit by creating a related Deposit.
                DepositFactory(
                    ledger=ledger,
                    transaction=initial_transaction,
                    desired_deposit_quantity=initial_transaction.quantity,
                )
            else:
                # Keep it a legacy initial deposit by NOT creating a related Deposit.
                expected_legacy_initial_transactions.append(initial_transaction)
            # Throw in a few spend, deposit, and adjustment transactions for fun.
            TransactionFactory(ledger=ledger, quantity=-10)
            TransactionFactory(ledger=ledger, quantity=-10)
            DepositFactory(ledger=ledger, desired_deposit_quantity=50)
            tx_to_adjust = TransactionFactory(ledger=ledger, quantity=-5)
            AdjustmentFactory(ledger=ledger, adjustment_quantity=5, transaction_of_interest=tx_to_adjust)

        actual_legacy_initial_transactions = migration_utils.find_legacy_initial_transactions(Transaction)
        assert set(actual_legacy_initial_transactions) == set(expected_legacy_initial_transactions)
