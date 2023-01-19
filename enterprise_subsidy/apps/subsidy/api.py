"""
The python API.
"""

from openedx_ledger.utils import (
    create_idempotency_key_for_subsidy,
    create_idempotency_key_for_transaction,
)
from openedx_ledger.api import (
    create_ledger,
)

from enterprise_subsidy.apps.subsidy import models


def create_learner_credit_subsidy(customer_uuid, unit, **kwargs):
    """
    Create a subsidy record.
    Create a ledger with starting balance.
    Return the subsidy record.
    """
    subsidy, _ = models.LearnerCreditSubsidy.objects.get_or_create(
        customer_uuid=customer_uuid,
        unit=unit,
        defaults=kwargs,
    )

    if kwargs.get('ledger'):
        return subsidy

    ledger = create_ledger(
        unit=unit,
        idempotency_key=create_idempotency_key_for_subsidy(subsidy),
    )

    subsidy.ledger = ledger
    # The following condition is crafted to respect 0 as an explicit starting balance.
    if 'starting_balance' in kwargs and kwargs['starting_balance'] is not None:
        idpk = create_idempotency_key_for_transaction(subsidy, kwargs['starting_balance'])
        _ = subsidy.create_transaction(idpk, kwargs['starting_balance'], {})

    subsidy.save()
    return subsidy


def create_subscription_subsidy(
        customer_uuid,
        subscription_plan_uuid,
        unit,
        do_sync=False,
        **kwargs,
):
    """
    Create and provision a SubscriptionSubsidy.

    An underlying ledger is created if not provided.
    """
    subsidy, _ = models.SubscriptionSubsidy.objects.get_or_create(
        customer_uuid=customer_uuid,
        subscription_plan_uuid=subscription_plan_uuid,
        unit=unit,
        defaults=kwargs,
    )

    if kwargs.get('ledger'):
        return subsidy

    ledger = create_ledger(
        unit=unit,
        idempotency_key=create_idempotency_key_for_subsidy(subsidy),
    )

    subsidy.ledger = ledger
    # The following condition is crafted to respect 0 as an explicit starting balance.
    if 'starting_balance' in kwargs and kwargs['starting_balance'] is not None:
        idpk = create_idempotency_key_for_transaction(subsidy, kwargs['starting_balance'])
        _ = subsidy.create_transaction(idpk, kwargs['starting_balance'], {})

        if do_sync and subscription_plan_uuid:
            sync_subscription(subsidy, subscription_plan_uuid)

    subsidy.save()
    return subsidy


def sync_subscription(subsidy, **metadata):
    current_balance = subsidy.current_balance()

    if current_balance > 0:
        # fine, zero out the ledger
        # TODO: sync one license uuid per transaction record.
        idpk = create_idempotency_key_for_transaction(subsidy, current_balance * -1, **metadata)
        subsidy.create_transaction(idpk, current_balance * -1, {})

    # ...but there's a lot more to sync'ing

    if subsidy.current_balance() != 0:
        raise Exception('ledger still not zerod')
