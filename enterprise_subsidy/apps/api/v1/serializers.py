"""
Serializers for the enterprise-subsidy API.
"""
from logging import getLogger
from urllib.parse import urljoin

from django.conf import settings
from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from openedx_ledger.models import LedgerLockAttemptFailed, Reversal, Transaction, UnitChoices
from requests.exceptions import HTTPError
from rest_framework import serializers

from enterprise_subsidy.apps.fulfillment.api import FulfillmentException
from enterprise_subsidy.apps.subsidy.models import (
    ContentNotFoundForCustomerException,
    PriceValidationError,
    RevenueCategoryChoices,
    Subsidy
)

logger = getLogger(__name__)


class SubsidySerializer(serializers.ModelSerializer):
    """
    Serializer for the `Subsidy` model.
    """
    current_balance = serializers.SerializerMethodField(help_text="The current (remaining) balance of this subsidy.")
    is_active = serializers.BooleanField(read_only=True, help_text="Whether this subsidy is currently active.")

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
            "is_active",
            # In the MVP implementation, there are only learner_credit subsidies.  Uncomment after subscription
            # subsidies are introduced.
            # "subsidy_type",
        ]

        read_only_fields = [
            "uuid",
            "starting_balance",
            "current_balance",
        ]

    @extend_schema_field(serializers.IntegerField)
    def get_current_balance(self, obj) -> int:
        return obj.current_balance()


class ReversalSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Reversal` model.
    """
    metadata = serializers.SerializerMethodField(
        help_text="Any additional metadata that a client may want to associate with this Reversal instance."
    )

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

    @extend_schema_field(serializers.JSONField)
    def get_metadata(self, obj) -> dict:
        """
        Properly serialize this json/dict
        http://web.archive.org/web/20230427144910/https://romansorin.com/blog/using-djangos-jsonfield-you-probably-dont-need-it-heres-why
        """
        return obj.metadata


class TransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for the `Transaction` model.

    When using this serializer on a queryset, it can help with performance to select_related reversals:

      Transaction.objects.select_related("reversal")
    """
    unit = serializers.SerializerMethodField(
        help_text="The unit in which this transaction's quantity is denominated."
    )
    transaction_status_api_url = serializers.SerializerMethodField(
        help_text="The URL to the transaction status API endpoint for this transaction."
    )
    courseware_url = serializers.SerializerMethodField(
        help_text=(
            "The URL to the courseware page for this transaction's content_key."
            "The courseware_url today only supports OCM courses, and should not be used for external, "
            "non-OCM course types."
        )
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
            "lms_user_email",
            "content_key",
            "content_title",
            "quantity",
            "unit",  # Manually fetch from parent ledger via get_unit().
            "fulfillment_identifier",
            "subsidy_access_policy_uuid",
            "metadata",
            "created",
            "modified",
            "reversal",  # Note that the `reversal` field is found via reverse relationship.
            "external_reference",  # Note that the `external_reference` field is found via reverse relationship.
            "transaction_status_api_url",
            "courseware_url",
        ]

    @extend_schema_field(serializers.URLField)
    def get_transaction_status_api_url(self, obj) -> str:
        """
        Helper to get the transaction status API URL from context
        """
        return urljoin(settings.ENTERPRISE_SUBSIDY_URL, reverse('api:v1:transaction-detail', args=[obj.uuid]))

    @extend_schema_field(serializers.URLField)
    def get_courseware_url(self, obj) -> str:
        """
        Helper method to get the courseware URL for this transaction's content_key.
        The courseware_url today only supports OCM courses, and should not be used for external, non-OCM course types.
        """
        path = f'course/{obj.content_key}/home'
        return urljoin(settings.FRONTEND_APP_LEARNING_URL, path)

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
    metadata = serializers.JSONField(
        help_text="Any additional metadata that a client may want to associate with this Transaction instance.",
        required=False,
        allow_null=True,
    )
    requested_price_cents = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text=(
            'The price, in USD cents, at which the caller requests the redemption be made. Must be >= 0.'
        ),
        min_value=0,
    )

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
            'metadata',
            'requested_price_cents',
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
        Gets or creates a Transaction record via the `Subsidy.redeem()` method.

        If an existing transaction is found with the same ledger and idempotency_key, that transaction is returned.
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
                requested_price_cents=validated_data.get('requested_price_cents'),
                metadata=validated_data.get('metadata'),
            )
        except LedgerLockAttemptFailed as exc:
            logger.exception(
                f'Encountered a lock failure while creating transaction for {validated_data} '
                f'in subsidy {subsidy.uuid}'
            )
            raise exc
        except HTTPError as exc:
            raise exc
        except ContentNotFoundForCustomerException as exc:
            logger.exception(
                f'Could not find content while creating transaction for {validated_data}'
                f'in subsidy {subsidy.uuid}'
            )
            raise exc
        except PriceValidationError as exc:
            logger.error(
                f'Invalid price requested for {validated_data} in subsidy {subsidy.uuid}'
            )
            raise exc
        except FulfillmentException as exc:
            logger.error(
                f'Error fulfilling transactions for {validated_data} in subsidy {subsidy.uuid}'
            )
            raise exc
        except Exception as exc:
            logger.exception(
                f'Encountered an exception while creating transaction for {validated_data}'
                f'in subsidy {subsidy.uuid}'
            )
            raise TransactionCreationError(str(exc)) from exc
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
    all_transactions = TransactionSerializer(
        required=False,
        allow_null=True,
        many=True,
        help_text=(
            'All existing transactions for the requested combination of (subsidy, access policy, lms_user_id, '
            'content_key).  This includes active (committed without reversal), reversed, failed, pending, or created '
            'transactions.'
        ),
    )
    active = serializers.BooleanField(
        default=False,
        help_text='Whether the subsidy is considered `is_active` and not expired.'
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
        help_text=(
            "Identifier of the upstream Salesforce object that represents the deal that led to the creation of this "
            "Subsidy. For test subsidy records, see the note below about ``default_internal_only``."
        ),
    )
    default_title = serializers.CharField(
        required=True,
        help_text="A human-readable title decided by the staff that is provisioning this Subisdy for the customer.",
    )
    default_enterprise_customer_uuid = serializers.UUIDField(
        required=True,
        help_text="UUID of the enterprise customer assigned this Subsidy.",
    )
    default_active_datetime = serializers.DateTimeField(
        required=True,
        help_text="The datetime when this Subsidy is considered active.  If null, this Subsidy is considered active."
    )
    default_expiration_datetime = serializers.DateTimeField(
        required=True,
        help_text="The datetime when this Subsidy is considered expired.  If null, this Subsidy is considered active."
    )
    default_unit = serializers.CharField(
        required=True,
        help_text="Unit of currency used for all values of quantity for this Subsidy and associated transactions.",
    )
    default_starting_balance = serializers.IntegerField(
        required=True,
        help_text="The positive balance this Subidy will be initially provisioned to start with.",
    )
    default_revenue_category = serializers.ChoiceField(
        RevenueCategoryChoices.CHOICES,
        required=True,
        help_text=(
            'Control how revenue is recognized for subsidized enrollments.  In spirit, this is equivalent to the '
            '"Cataloge Category" for Coupons.  This field is only used downstream analytics and does not change any '
            'business logic.'
        ),
    )
    default_internal_only = serializers.BooleanField(
        required=True,
        help_text=(
            "If set, this subsidy will not be customer facing, nor have any influence on enterprise customers."
            "If ``default_internal_only`` is False and an existing subsidy is "
            "found with the given ``reference_id``, all `default_*` arguments are ignored "
            "and this view returns that existing record. "
            "However, when ``default_internal_only`` is True, this view will "
            "simply create a new record, regardless of any existing records "
            "with the same ``reference_id`` (we assume that the reference_id is "
            "essentially meaningless for test subsidy records)."
        ),
    )


class SubsidyUpdateRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for updating a subsidy
    """

    class Meta:
        """
        Meta class for SubsidySerializer.
        """
        model = Subsidy
        fields = [
            "title",
            "enterprise_customer_uuid",
            "active_datetime",
            "expiration_datetime",
            "unit",
            "reference_id",
            "reference_type",
            "internal_only",
            "revenue_category",
            # In the MVP implementation, there are only learner_credit subsidies.  Uncomment after subscription
            # subsidies are introduced.
            # "subsidy_type",
        ]

    def to_representation(self, instance):
        """
        Once a Subsidy has been created, we want to serialize
        more fields from the instance than are required in this, the input serializer.
        """
        subsidy_serializer = SubsidySerializer(instance)
        return subsidy_serializer.data
