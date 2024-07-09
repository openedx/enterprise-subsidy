"""
Backfill initial deposits.

Necessarily, this also backfills SalesContractReferenceProvider objects based on the values currently defined via
SubsidyReferenceChoices.

Note this has no reverse migration logic. Attempts to rollback the deployment which includes this PR will not delete
(un-backfill) the deposits created during the forward migration.
"""
import django.utils.timezone
from django.db import migrations

from enterprise_subsidy.apps.subsidy.migration_utils import find_legacy_initial_transactions
from enterprise_subsidy.apps.subsidy.models import SubsidyReferenceChoices


def forwards_func(apps, schema_editor):
    """
    The core logic of this migration.
    """
    # We get the models from the versioned app registry; if we directly import it, it'll be the wrong version.
    Transaction = apps.get_model("openedx_ledger", "Transaction")
    Deposit = apps.get_model("openedx_ledger", "Deposit")
    HistoricalDeposit = apps.get_model("openedx_ledger", "HistoricalDeposit")
    SalesContractReferenceProvider = apps.get_model("openedx_ledger", "SalesContractReferenceProvider")

    # Idempotently duplicate all SubsidyReferenceChoices into SalesContractReferenceProvider.
    sales_contract_reference_providers = {}
    for slug, name in SubsidyReferenceChoices.CHOICES:
        sales_contract_reference_providers[slug], _ = SalesContractReferenceProvider.objects.get_or_create(
            slug=slug,
            defaults={"name": name},
        )

    # Fetch all "legacy" initial transactions.
    legacy_initial_transactions = find_legacy_initial_transactions(Transaction).select_related("ledger__subsidy")

    # Construct all missing Deposits and HistoricalDeposits to backfill, but do not save them yet.
    #
    # Note: The reason we need to manually create historical objects is that Django's bulk_create() built-in does not
    # call post_save hooks, which is normally where history objects are created. Next you might ask why we don't just
    # use django-simple-history's bulk_create_with_history() utility function: that's because it attempts to access the
    # custom simple history model manager, but unfortunately custom model attributes are unavailable from migrations.
    deposits_to_backfill = []
    historical_deposits_to_backfill = []
    for tx in legacy_initial_transactions:
        deposit_fields = {
            "ledger": tx.ledger,
            "transaction": tx,
            "desired_deposit_quantity": tx.quantity,
            "sales_contract_reference_id": tx.ledger.subsidy.reference_id,
            "sales_contract_reference_provider": sales_contract_reference_providers[tx.ledger.subsidy.reference_type],
        }
        deposit = Deposit(**deposit_fields)
        historical_deposit = HistoricalDeposit(
            uuid=deposit.uuid,
            history_date=django.utils.timezone.now(),
            history_type="+",
            history_change_reason="Data migration to backfill initial deposits",
            **deposit_fields,
        )
        deposits_to_backfill.append(deposit)
        historical_deposits_to_backfill.append(historical_deposit)

    # Finally, save the missing Deposits and HistoricalDeposits in bulk.
    Deposit.objects.bulk_create(deposits_to_backfill, batch_size=50)
    HistoricalDeposit.objects.bulk_create(historical_deposits_to_backfill, batch_size=50)


class Migration(migrations.Migration):
    """
    Migration for backfilling initial deposits.
    """
    dependencies = [
        ("subsidy", "0021_alter_historicalsubsidy_options"),
        # This migration relies on Deposit.sales_contract_reference_id being an optional field. Django alone cannot
        # possibly know about this dependency without our help.
        ("openedx_ledger", "0012_optional_deposit_sales_contract_reference"),
    ]

    operations = [
        migrations.RunPython(forwards_func),
    ]
