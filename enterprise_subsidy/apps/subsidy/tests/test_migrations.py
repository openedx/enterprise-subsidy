"""
Test migrations.
"""
import uuid

import django.utils.timezone
import pytest
from openedx_ledger.constants import INITIAL_DEPOSIT_TRANSACTION_SLUG
from openedx_ledger.models import TransactionStateChoices


@pytest.mark.django_db
@pytest.mark.parametrize(
    "initial_deposit_exists,subsidy_exists,subsidy_reference_id,subsidy_reference_type",
    [
        (False, False, None,     "salesforce_opportunity_line_item"),
        (False, True,  None,     "salesforce_opportunity_line_item"),
        # This is the most common case that we're targetting in prod.
        (False, True,  "abc123", "salesforce_opportunity_line_item"),
        # This specific case defends against a case in stage where there was a Subsidy with a bogus reference_type.
        (False, True,  "abc123", "bogus_made_up"),
        (True,  False, None,     "salesforce_opportunity_line_item"),
        (True,  True,  None,     "salesforce_opportunity_line_item"),
        (True,  True,  "abc123", "salesforce_opportunity_line_item"),
    ],
)
def test_migration_0022_backfill_initial_deposits(
    migrator,
    initial_deposit_exists,
    subsidy_exists,
    subsidy_reference_id,
    subsidy_reference_type,
):
    """
    Test Backfilling initial deposits via data migration.
    """
    old_state = migrator.apply_initial_migration([
        ("subsidy", "0021_alter_historicalsubsidy_options"),
        ("openedx_ledger", "0012_optional_deposit_sales_contract_reference"),
    ])

    Subsidy = old_state.apps.get_model("subsidy", "Subsidy")
    Ledger = old_state.apps.get_model("openedx_ledger", "Ledger")
    Transaction = old_state.apps.get_model("openedx_ledger", "Transaction")
    Deposit = old_state.apps.get_model("openedx_ledger", "Deposit")
    HistoricalDeposit = old_state.apps.get_model("openedx_ledger", "HistoricalDeposit")
    SalesContractReferenceProvider = old_state.apps.get_model("openedx_ledger", "SalesContractReferenceProvider")

    ledger = Ledger.objects.create()
    subsidy = None
    if subsidy_exists:
        subsidy = Subsidy.objects.create(
            ledger=ledger,
            starting_balance=100,
            reference_id=subsidy_reference_id,
            reference_type=subsidy_reference_type,
            enterprise_customer_uuid=uuid.uuid4(),
        )
    transaction = Transaction.objects.create(
        ledger=ledger,
        idempotency_key=INITIAL_DEPOSIT_TRANSACTION_SLUG,
        quantity=subsidy.starting_balance if subsidy_exists else 100,
        state=TransactionStateChoices.COMMITTED
    )
    if initial_deposit_exists:
        sales_contract_reference_provider = None
        if subsidy_exists:
            sales_contract_reference_provider = SalesContractReferenceProvider.objects.create(
                slug=subsidy.reference_type,
                name="Foo Bar",
            )
        Deposit.objects.create(
            ledger=ledger,
            desired_deposit_quantity=transaction.quantity,
            transaction=transaction,
            sales_contract_reference_id=subsidy_reference_id,  # Sometimes this is None.
            sales_contract_reference_provider=sales_contract_reference_provider,
        )
        HistoricalDeposit.objects.create(
            ledger=ledger,
            desired_deposit_quantity=transaction.quantity,
            transaction=transaction,
            sales_contract_reference_id=subsidy_reference_id,
            sales_contract_reference_provider=sales_contract_reference_provider,
            history_date=django.utils.timezone.now(),
            history_type="+",
            history_change_reason="Data migration to backfill initial deposits",
        )

    new_state = migrator.apply_tested_migration(
        ("subsidy", "0022_backfill_initial_deposits"),
    )
    Deposit = new_state.apps.get_model("openedx_ledger", "Deposit")
    HistoricalDeposit = new_state.apps.get_model("openedx_ledger", "HistoricalDeposit")

    # Make sure there is exactly one deposit, suggesting that if one already existed it is not re-created.
    assert Deposit.objects.all().count() == 1
    assert HistoricalDeposit.objects.all().count() == 1

    # Finally check that all the deposit values are correct.
    deposit = Deposit.objects.first()
    assert deposit.ledger.uuid == ledger.uuid
    assert deposit.desired_deposit_quantity == 100
    assert deposit.transaction.uuid == transaction.uuid
    if subsidy_exists:
        assert deposit.sales_contract_reference_id == subsidy_reference_id
        if subsidy_reference_type == "salesforce_opportunity_line_item":
            assert deposit.sales_contract_reference_provider.slug == subsidy.reference_type
        else:
            assert Deposit.objects.first().sales_contract_reference_provider is None
    else:
        assert deposit.sales_contract_reference_id is None
        assert deposit.sales_contract_reference_provider is None

    historical_deposit = HistoricalDeposit.objects.first()
    assert historical_deposit.ledger.uuid == ledger.uuid
    assert historical_deposit.desired_deposit_quantity == 100
    assert historical_deposit.transaction.uuid == transaction.uuid
    assert historical_deposit.sales_contract_reference_id == deposit.sales_contract_reference_id
    assert historical_deposit.sales_contract_reference_provider == deposit.sales_contract_reference_provider
    assert historical_deposit.history_type == "+"
    assert historical_deposit.history_change_reason == "Data migration to backfill initial deposits"
