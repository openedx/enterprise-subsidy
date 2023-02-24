"""
The python API.
"""

from openedx_ledger.api import create_ledger
from openedx_ledger.utils import create_idempotency_key_for_subsidy, create_idempotency_key_for_transaction

from enterprise_subsidy.apps.subsidy.models import Subsidy


def get_or_create_learner_credit_subsidy(
    reference_id, default_title, default_enterprise_customer_uuid, default_unit, default_starting_balance,
):
    """
    Get or create a new learner credit subsidy and ledger with the given defaults.

    Notes:
        * If an existing subsidy is found with the given `reference_id`, all `default_*` arguments are ignored.

    Args:
        reference_id (str): ID of the originating salesforce opportunity product.
        default_title (str): Human-readable title of the new subsidy.
        default_enterprise_customer_uuid (uuid.UUID): UUID of the enterprise customer.
        default_unit (str): value unit identifier (see openedx_ledger.models.UnitChoices).
        default_starting_balance (int): The default starting balance if creating a new subsidy and ledger.

    Returns:
        tuple(enterprise_subsidy.apps.subsidy.models.Subsidy, bool):
            The subsidy record, and an bool that is true if a new subsidy+ledger was created.

    Raises:
        MultipleObjectsReturned if two or more subsidy records with the given reference_id already exists.
    """
    subsidy_defaults = {
        'title': default_title,
        'starting_balance': default_starting_balance,
        'enterprise_customer_uuid': default_enterprise_customer_uuid,
        'unit': default_unit,
    }
    subsidy, created = Subsidy.objects.get_or_create(
        reference_id=reference_id,
        defaults=subsidy_defaults,
    )

    if not subsidy.ledger:
        ledger = create_ledger(unit=default_unit, idempotency_key=create_idempotency_key_for_subsidy(subsidy))
        subsidy.ledger = ledger
        # Seed the new ledger with its first transaction that reflects the requested starting balance:
        idpk = create_idempotency_key_for_transaction(subsidy, default_starting_balance)
        _ = subsidy.create_transaction(idpk, default_starting_balance, {})

    subsidy.save()
    return (subsidy, created)
