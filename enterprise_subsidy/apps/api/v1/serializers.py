"""
Serializers for the enterprise-subsidy API.
"""

from openedx_ledger.models import Transaction
from rest_framework import serializers

from enterprise_subsidy.apps.subsidy.models import Subsidy


class SubsidySerializer(serializers.ModelSerializer):
    """
    Serializer for the `SubscriptionPlan` model.
    """
    class Meta:
        """
        Meta class for SubsidySerializer.
        """
        model = Subsidy
        fields = [
            "uuid",
            "title",
            "enterprise_customer_uuid",
            "active_datetime",
            "expiration_datetime",
            "unit",
            "reference_id",
            "reference_type",
            # TODO: serialize derived fields:
            # "subsidy_type",  # which Subsidy subtype is this?
            # "remaining_balance",  # calculate the ledger.balance()
        ]


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for the `SubscriptionPlan` model.
    """
    class Meta:
        """
        Meta class for SubsidySerializer.
        """
        model = Transaction
        fields = [
            "uuid",
            "state",
            "idempotency_key",
            "lms_user_id",
            "content_key",
            "quantity",
            "reference_id",
            "reference_type",
            "subsidy_access_policy_uuid",
            "metadata",
            "created",
            "modified",
            # TODO: serialize derived fields:
            # "unit",  # Get from parent ledger.
            # "reversals",  # Calculate by querying reversals.
        ]
