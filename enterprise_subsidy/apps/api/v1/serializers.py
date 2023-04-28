"""
Serializers for the enterprise-subsidy API.
"""
from logging import getLogger

from drf_spectacular.utils import extend_schema_field
from openedx_ledger.models import LedgerLockAttemptFailed, Reversal, Transaction, UnitChoices
from rest_framework import serializers

from enterprise_subsidy.apps.subsidy.models import Subsidy

logger = getLogger(__name__)


class SubsidySerializer(serializers.ModelSerializer):
    """
    Serializer for the `Subsidy` model.
    """
    current_balance = serializers.SerializerMethodField(help_text="The current (remaining) balance of this subsidy.")

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

    @extend_schema_field(serializers.IntegerField)
    def get_current_balance(self, obj) -> int:
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
    # http://web.archive.org/web/20230427144910/https://romansorin.com/blog/using-djangos-jsonfield-you-probably-dont-need-it-heres-why
    metadata = serializers.SerializerMethodField(
        help_text="Any additional metadata that a client may want to associate with this Transaction instance."
    )

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

    @extend_schema_field(serializers.JSONField)
    def get_metadata(self, obj) -> dict:
        """
        Properly serialize this json/dict
        http://web.archive.org/web/20230427144910/https://romansorin.com/blog/using-djangos-jsonfield-you-probably-dont-need-it-heres-why
        """
        return obj.metadata

    @extend_schema_field(serializers.ChoiceField(UnitChoices.CHOICES))
    def get_unit(self, obj) -> str:
        """
        Simply fetch the unit slug from the parent Ledger.

        Returns:
            str: unit slug.
        """
        return obj.ledger.unit if obj.ledger else None


class TransactionCreationError(Exception):
    """
    Generic exception related to errors during transaction creation.
    """


class TransactionCreationRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for creating instances of the `Transaction` model.
    """

    class Meta:
        """
        Meta class for TransactionSerializer.
        """
        model = Transaction
        fields = [
            'idempotency_key',
            'lms_user_id',
            'content_key',
            'subsidy_access_policy_uuid',
        ]
        # Override lms_user_id, content_key, and subsidy_access_policy_uuid to each be required;
        # their model field definitions have `required=False`.
        extra_kwargs = {
            'idempotency_key': {'required': False},
            'lms_user_id': {'required': True},
            'content_key': {'required': True},
            'subsidy_access_policy_uuid': {'required': True},
        }

    def to_representation(self, instance):
        """
        Once a Transaction has been created, we want to serialize
        more fields from the instance than are required in this, the input serializer.
        """
        read_serializer = TransactionSerializer(instance)
        return read_serializer.data

    @property
    def calling_view(self):
        """
        Helper to get the calling DRF view object from context
        """
        return self.context['view']

    def create(self, validated_data):
        """
        Creates a new Transaction record via the `Subsidy.redeem()` method.
        """
        # subsidy() is a convenience property on the instance of the Transaction view class that uses
        # this serializer.
        subsidy = self.calling_view.subsidy

        try:
            transaction, created = subsidy.redeem(
                validated_data['lms_user_id'],
                validated_data['content_key'],
                validated_data['subsidy_access_policy_uuid'],
                idempotency_key=validated_data.get('idempotency_key'),
            )
        except LedgerLockAttemptFailed as exc:
            logger.exception(
                f'Encountered a lock failure while creating transaction for {validated_data} '
                f'in subsidy {subsidy.uuid}'
            )
            raise exc
        except Exception as exc:
            logger.exception(
                f'Encountered an exception while creating transaction for {validated_data}'
                f'in subsidy {subsidy.uuid}'
            )
            raise TransactionCreationError('Encountered an exception while creating transaction') from exc
        if not transaction:
            logger.error(
                f'Transaction was None after attempting to redeem for {validated_data}'
                f'in subsidy {subsidy.uuid}'
            )
            raise TransactionCreationError('Transaction was None after attempting to redeem')

        self.calling_view.set_transaction_was_created(created)
        return transaction


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
