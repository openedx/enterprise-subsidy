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
            "starting_balance",
            "internal_only",
            "revenue_category",
            # In the MVP implementation, there are only learner_credit subsidies.  Uncomment after subscription
            # subsidies are introduced.
            # "subsidy_type",
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

    When using this serializer on a queryset, it can help with performance to select_related reversals:

      Transaction.objects.select_related("reversal")
    """
    unit = serializers.SerializerMethodField(
        help_text="The unit in which this transaction's quantity is denominated."
    )
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
            "fulfillment_identifier",
            "subsidy_access_policy_uuid",
            "metadata",
            "created",
            "modified",
            "reversal",  # Note that the `reversal` field is found via reverse relationship.
            "external_reference",  # Note that the `external_reference` field is found via reverse relationship.
        ]

    def get_unit(self, obj):
        """
        Simply fetch the unit slug from the parent Ledger.

        Returns:
            str: unit slug.
        """
        return obj.ledger.unit if obj.ledger else None


# pylint: disable=abstract-method
class CanRedeemResponseSerializer(serializers.Serializer):
    """
    Serializer for providing responses to queries about redeemability
    for a particular user id and content_key.
    """
    can_redeem = serializers.BooleanField(
        default=True,
        help_text='Whether the provided learner/content can redeem via this Subsidy.'
    )
    content_price = serializers.IntegerField(
        default=1,
        help_text='The price of the queried content_key.',
    )
    unit = serializers.CharField(
        default='usd_cents',
        help_text='The unit in which price is denominated.'
    )
    existing_transaction = TransactionSerializer(
        required=False,
        allow_null=True,
    )


class ExceptionSerializer(serializers.Serializer):
    """
    Read-only serializer for responding with data about errors.
    """
    detail = serializers.CharField(
        help_text="A description of the reason for the error.",
    )


# pylint: disable=abstract-method
class SubsidyCreationRequestSerializer(serializers.Serializer):
    """
    Serializer for creating a subsidy request
    """
    reference_id = serializers.CharField(
        required=True,
        help_text="Reference id",
    )
    default_title = serializers.CharField(
        required=True,
    )
    default_enterprise_customer_uuid = serializers.UUIDField(
        required=True,
    )
    default_unit = serializers.CharField(
        required=True,
    )
    default_starting_balance = serializers.IntegerField(
        required=True,
    )
    default_revenue_category = serializers.CharField(
        required=True,
    )
    default_internal_only = serializers.BooleanField(
        required=True,
    )
