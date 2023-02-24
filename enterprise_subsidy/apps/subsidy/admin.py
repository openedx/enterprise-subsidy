"""
Admin configuration for subsidy models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from enterprise_subsidy.apps.subsidy.models import Subsidy


@admin.register(Subsidy)
class SubsidyAdmin(SimpleHistoryAdmin):
    class Meta:
        model = Subsidy
        fields = '__all__'
