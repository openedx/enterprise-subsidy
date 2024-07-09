"""
Helper functions for data migrations.
"""
from django.db.models import F, Window
from django.db.models.functions import FirstValue
# This utils module is imported by migrations, so never import any models directly here, nor any modules that import
# models in turn.
from openedx_ledger.constants import INITIAL_DEPOSIT_TRANSACTION_SLUG


def find_legacy_initial_transactions(transaction_cls):
    """
    Heuristic to identify "legacy" initial transactions.

    An initial transaction is one that has the following traits:
    * Is chronologically the first transaction for a Ledger.
    * Contains a hint in its idempotency key which indicates that it is an initial deposit.
    * Has a positive quantity.

    A legacy initial transaction is one that has the following additional traits:
    * does not have a related Deposit.
    """
    # All transactions which are chronologically the first in their respective ledgers.
    first_transactions = transaction_cls.objects.annotate(
        first_tx_uuid=Window(
            expression=FirstValue('uuid'),
            partition_by=['ledger'],
            order_by=F('created').asc(),  # "first chronologically" above means first created.
        ),
    ).filter(uuid=F('first_tx_uuid'))

    # Further filter first_transactions to find ones that qualify as _initial_ and _legacy_.
    legacy_initial_transactions = first_transactions.filter(
        # Traits of an _initial_ deposit:
        idempotency_key__contains=INITIAL_DEPOSIT_TRANSACTION_SLUG,
        quantity__gte=0,
        # Traits of a _legacy_ initial deposit:
        deposit__isnull=True,
    )
    return legacy_initial_transactions
