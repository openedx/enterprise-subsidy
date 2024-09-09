"""
V2 Serializers for the enterprise-subsidy API.
"""
import logging

import openedx_ledger.api
from openedx_ledger.models import Deposit, SalesContractReferenceProvider
from rest_framework import serializers

logger = logging.getLogger(__name__)


class DepositSerializer(serializers.ModelSerializer):
    """
    Read-only response serializer for the `Deposit` model.
    """
    # Unless we override this field, it will use the primary key via PriaryKeyRelatedField which is less useful than the
    # slug.
    sales_contract_reference_provider = serializers.SlugRelatedField(
        slug_field='slug',
        many=False,
        read_only=True,
    )

    class Meta:
        """
        Meta class for DepositSerializer.
        """
        model = Deposit
        fields = [
            'uuid',
            'ledger',
            'desired_deposit_quantity',
            'transaction',
            'sales_contract_reference_id',
            'sales_contract_reference_provider',
        ]


class DepositCreationError(Exception):
    """
    Generic exception related to errors during transaction creation.
    """


class DepositCreationRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for creating instances of the `Transaction` model.
    """
    sales_contract_reference_provider = serializers.SlugRelatedField(
        slug_field='slug',
        many=False,
        queryset=SalesContractReferenceProvider.objects.all(),
    )
    idempotency_key = serializers.CharField(
        help_text=(
            "An optional idempotency key that a client may want to associate with the "
            "related Transaction instance to be created."
        ),
        required=False,
    )
    metadata = serializers.JSONField(
        help_text=(
            "Any additional metadata that a client may want to associate with the "
            "related Transaction instance to be created."
        ),
        allow_null=True,
        required=False,
    )

    class Meta:
        """
        Meta class for DepositCreationSerializer.
        """
        model = Deposit
        fields = [
            'desired_deposit_quantity',
            'sales_contract_reference_id',
            'sales_contract_reference_provider',
            'idempotency_key',
            'metadata',
        ]
        extra_kwargs = {
            'desired_deposit_quantity': {
                'required': True,
                'min_value': 1,
            },
            'sales_contract_reference_id': {'required': True},
            'sales_contract_reference_provider': {'required': True},
            'idempotency_key': {'required': False},
            'metadata': {'required': False},
        }

    def to_representation(self, instance):
        """
        Once a Deposit has been created, we want to serialize more fields from the instance than are required in this,
        the input serializer.
        """
        read_serializer = DepositSerializer(instance)
        return read_serializer.data

    @property
    def calling_view(self):
        """
        Helper to get the calling DRF view object from context
        """
        return self.context['view']

    def create(self, validated_data):
        """
        Gets or creates a Deposit record via the `openedx_ledger.api.create_deposit()` method.

        If an existing Deposit is found with the same ledger, quantity, and related transaction idempotency_key, that
        Desposit is returned.

        Raises:
          enterprise_subsidy.apps.api.v2.serializers.deposits.DepositCreationError:
              Catch-all exception for when any other problem occurs during deposit creation. One possibility is that the
              caller attempted to create the same deposit twice.
        """
        # subsidy() is a convenience property on the instance of the view class that uses this serializer.
        subsidy = self.calling_view.subsidy

        try:
            deposit = openedx_ledger.api.create_deposit(
                ledger=subsidy.ledger,
                quantity=validated_data['desired_deposit_quantity'],
                sales_contract_reference_id=validated_data['sales_contract_reference_id'],
                sales_contract_reference_provider=validated_data['sales_contract_reference_provider'],
                idempotency_key=validated_data.get('idempotency_key'),
                **(validated_data.get('metadata') or {}),
            )
        except openedx_ledger.api.DepositCreationError as exc:
            logger.error(
                'Encountered DepositCreationError while creating Deposit in subsidy %s using values %s',
                subsidy.uuid,
                validated_data,
            )
            raise DepositCreationError(str(exc)) from exc
        if not deposit:
            logger.error(
                'Deposit was None after attempting deposit creation in subsidy %s using values %s',
                subsidy.uuid,
                validated_data,
            )
            raise DepositCreationError('Deposit was None after attempting to redeem')

        self.calling_view.set_created(True)
        return deposit
