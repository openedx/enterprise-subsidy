"""
Admin configuration for subsidy models.
"""
from django.contrib import admin
from .models import LearnerCreditSubsidy, SubscriptionSubsidy

@admin.register(LearnerCreditSubsidy)
class LearnerCreditSubsidyAdmin(admin.ModelAdmin):
    class Meta:
        model = LearnerCreditSubsidy
        fields = '__all__'


@admin.register(SubscriptionSubsidy)
class SubscriptionSubsidyAdmin(admin.ModelAdmin):
    class Meta:
        model = SubscriptionSubsidy
        fields = '__all__'
