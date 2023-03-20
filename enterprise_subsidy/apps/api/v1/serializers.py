"""
Serializers for the enterprise-subsidy API.
"""

from openedx_ledger.models import Reversal, Transaction
from rest_framework import serializers

from enterprise_subsidy.apps.subsidy.models import Subsidy


class SubsidySerializer(serializers.ModelSerializer):
    """
    Serializer for the `Subsidy` model.
    """
    current_balance = serializers.SerializerMethodField()

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
            "current_balance",
            # TODO: serialize derived fields:
            # "subsidy_type",  # which Subsidy subtype is this?
        ]

    def get_current_balance(self, obj):
        return obj.current_balance()


class ReversalSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Reversal` model.
    """

    class Meta:
        """
        Meta class for ReversalSerializer.
        """
        model = Reversal
        fields = [
            "uuid",
            "state",
            "idempotency_key",
            "quantity",
            "metadata",
            "created",
            "modified",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Transaction` model.

    When using this serializer on a queryset, it can help with performance to prefectch the following:

      .prefetch_related("reversal")
    """
    unit = serializers.SerializerMethodField()
    reversal = ReversalSerializer(read_only=True)

    class Meta:
        """
        Meta class for TransactionSerializer.
        """
        model = Transaction
        fields = [
            "uuid",
            "state",
            "idempotency_key",
            "lms_user_id",
            "content_key",
            "quantity",
            "unit",  # Manually fetch from parent ledger via get_unit().
            "reference_id",
            "reference_type",
            "subsidy_access_policy_uuid",
            "metadata",
            "created",
            "modified",
            "reversal",  # Note that the `reversal` field is found via reverse relationship.
        ]

    def get_unit(self, obj):
        """
        Simply fetch the unit slug from the parent Ledger.

        Returns:
            str: unit slug.
        """
        return obj.ledger.unit if obj.ledger else None
