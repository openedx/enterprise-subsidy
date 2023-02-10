"""
Admin configuration for subsidy models.
"""
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import LearnerCreditSubsidy, SubscriptionSubsidy


@admin.register(LearnerCreditSubsidy)
class LearnerCreditSubsidyAdmin(SimpleHistoryAdmin):
    class Meta:
        model = LearnerCreditSubsidy
        fields = '__all__'


@admin.register(SubscriptionSubsidy)
class SubscriptionSubsidyAdmin(SimpleHistoryAdmin):
    class Meta:
        model = SubscriptionSubsidy
        fields = '__all__'
