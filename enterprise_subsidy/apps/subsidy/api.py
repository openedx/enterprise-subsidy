"""
The python API.
"""
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
    return (subsidy, created)
