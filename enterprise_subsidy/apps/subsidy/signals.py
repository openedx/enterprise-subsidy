"""
Signals related to operations on ``subsidy`` models.
"""
from django.db.models.signals import pre_save
from django.dispatch import receiver
from openedx_ledger.api import create_ledger
from openedx_ledger.models import SalesContractReferenceProvider

from .models import Subsidy, SubsidyReferenceChoices


@receiver(pre_save, sender=Subsidy)
def subsidy_pre_save(sender, instance, *args, **kwargs):  # pylint: disable=unused-argument
    """
    If the Subsidy ``instance`` is being created and does _not_ have
    an associated ledger, create one.
    params:
      sender: The Subsidy class.
      instance: An instance of a Subsidy model that is about to be saved.
    """
    # pylint: disable=protected-access
    if instance.ledger or not instance._state.adding:
        return

    # In order to call create_ledger() later, we first need to get or create a SalesContractReferenceProvider. In order
    # to avoid manual intervention, we mirror the SubsidyReferenceChoices selection into the
    # SalesContractReferenceProvider table as needed. The normal steady-state is to always just re-use (get) an existing
    # provider.
    subsidy_reference_choices = dict((slug, name) for slug, name in SubsidyReferenceChoices.CHOICES)
    sales_contract_reference_provider, _ = SalesContractReferenceProvider.objects.get_or_create(
        slug=instance.reference_type,
        defaults={"name": subsidy_reference_choices[instance.reference_type]},
    )

    # create_ledger() saves the ledger instance.
    # If a transaction for the starting_balance is created,
    # that transaction record is also saved during
    # the create_ledger() call.
    instance.ledger = create_ledger(  # pylint: disable=no-value-for-parameter,useless-suppression
        unit=instance.unit,
        subsidy_uuid=instance.uuid,
        initial_deposit=instance.starting_balance,
        sales_contract_reference_id=instance.reference_id,
        sales_contract_reference_provider=sales_contract_reference_provider,
    )
