"""
The python API.
"""

from openedx_ledger.api import create_ledger
from openedx_ledger.utils import create_idempotency_key_for_subsidy, create_idempotency_key_for_transaction

from enterprise_subsidy.apps.subsidy.models import LearnerCreditSubsidy, SubscriptionSubsidy


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
        tuple(enterprise_subsidy.apps.subsidy.models.LearnerCreditSubsidy, bool):
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
    subsidy, created = LearnerCreditSubsidy.objects.get_or_create(
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


def get_or_create_subscription_subsidy(
    reference_id,
    default_title,
    default_enterprise_customer_uuid,
    default_unit,
    default_starting_balance,
    default_subscription_plan_uuid,
    do_sync=False,
):
    """
    Get or create a new subscription subsidy and ledger with the given defaults.

    Notes:
        * If an existing subsidy is found with the given `reference_id`, all `default_*` arguments are ignored.

    Args:
        reference_id (str): ID of the originating salesforce opportunity product.
        default_title (str): Human-readable title of the new subsidy.
        default_enterprise_customer_uuid (uuid.UUID): UUID of the enterprise enterprise_customer.
        default_unit (str): value unit identifier (see openedx_ledger.models.UnitChoices).
        default_starting_balance (int): The default starting balance if creating a new subsidy and ledger.
        default_subscription_plan_uuid (int): The default starting balance if creating a new subsidy and ledger.
        do_sync (bool, Optional): Whether to perform sync_subscription(). TODO: describe what it does.

    Returns:
        tuple(enterprise_subsidy.apps.subsidy.models.SubscriptionSubsidy, bool):
            The subsidy record, and an bool that is true if a new subsidy+ledger was created.

    Raises:
        MultipleObjectsReturned if two or more subsidy records with the given reference_id already exists.
    """
    subsidy_defaults = {
        'title': default_title,
        'enterprise_customer_uuid': default_enterprise_customer_uuid,
        'unit': default_unit,
        'starting_balance': default_starting_balance,
        'subscription_plan_uuid': default_subscription_plan_uuid,
    }
    subsidy, created = SubscriptionSubsidy.objects.get_or_create(
        reference_id=reference_id,
        defaults=subsidy_defaults,
    )

    if not subsidy.ledger:
        ledger = create_ledger(unit=default_unit, idempotency_key=create_idempotency_key_for_subsidy(subsidy))
        subsidy.ledger = ledger
        # Seed the new ledger with its first transaction that reflects the requested starting balance:
        idpk = create_idempotency_key_for_transaction(subsidy, default_starting_balance)
        _ = subsidy.create_transaction(idpk, default_starting_balance, {})
        if do_sync and subsidy.subscription_plan_uuid:
            sync_subscription(subsidy)

    subsidy.save()
    return (subsidy, created)


def sync_subscription(subsidy, **metadata):
    """
    TODO: finish the design of this function.
    """
    current_balance = subsidy.current_balance()

    if current_balance > 0:
        # fine, zero out the ledger
        # TODO: sync one license uuid per transaction record.
        idpk = create_idempotency_key_for_transaction(subsidy, current_balance * -1, **metadata)
        subsidy.create_transaction(idpk, current_balance * -1, {})

    # ...but there's a lot more to sync'ing

    if subsidy.current_balance() != 0:
        raise Exception('ledger still not zerod')  # pylint: disable=broad-exception-raised
