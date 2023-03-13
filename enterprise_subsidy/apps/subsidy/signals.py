"""
Signals related to operations on ``subsidy`` models.
"""
from django.db.models.signals import pre_save
from django.dispatch import receiver
from openedx_ledger.api import create_ledger

from .models import Subsidy


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

    # create_ledger() saves the ledger instance.
    # If a transaction for the starting_balance is created,
    # that transaction record is also saved during
    # the create_ledger() call.
    instance.ledger = create_ledger(
        unit=instance.unit,
        subsidy_uuid=instance.uuid,
        initial_deposit=instance.starting_balance,
    )
