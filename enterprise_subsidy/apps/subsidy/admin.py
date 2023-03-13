"""
Admin configuration for subsidy models.
"""
from django.contrib import admin
from django.conf import settings
from openedx_ledger import api as ledger_api
from simple_history.admin import SimpleHistoryAdmin

from enterprise_subsidy.apps.subsidy.models import Subsidy


def can_modify():
    getattr(settings, 'ALLOW_LEDGER_MODIFICATION', False)


@admin.register(Subsidy)
class SubsidyAdmin(SimpleHistoryAdmin):
    class Meta:
        model = Subsidy
        fields = '__all__'

    _all_fields = [field.name for field in Subsidy._meta.get_fields()]
    readonly_fields = _all_fields
    if can_modify():
        readonly_fields = []
    
    def save_model(self, request, obj, form, change):
        """
        obj is a Subsidy object.
        """
        if not obj.ledger:
            ledger = ledger_api.create_ledger(
                unit=obj.unit,
                subsidy_uuid=obj.uuid,
                inital_deposit=obj.starting_balance,
            )
            obj.ledger = ledger
        super().save_model(request, obj, form, change)
