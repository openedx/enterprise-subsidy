"""
Tests for the serializers in the API.
"""
from uuid import uuid4

import ddt
from django.test import TestCase
from openedx_ledger.test_utils.factories import DepositFactory, SalesContractReferenceProviderFactory

from enterprise_subsidy.apps.api.v2.serializers.deposits import DepositCreationRequestSerializer, DepositSerializer
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory


@ddt.ddt
class TestDepositSerializer(TestCase):
    """
    Tests for the DepositSerializer.
    """
    @ddt.data(
        {
            "desired_deposit_quantity": 100,
            "sales_contract_reference_id": str(uuid4()),
            "set_sales_contract_reference_provider": True,
        },
        {
            "desired_deposit_quantity": 100,
            "sales_contract_reference_id": None,
            "set_sales_contract_reference_provider": False,
        },
    )
    @ddt.unpack
    def test_deposit_serializer(
        self,
        desired_deposit_quantity,
        sales_contract_reference_id,
        set_sales_contract_reference_provider,
    ):
        """
        Test that the DepositRequest serializer returns the correct values.
        """
        # Set up the deposit to serialize.
        subsidy = SubsidyFactory()
        sales_contract_reference_provider = None
        if set_sales_contract_reference_provider:
            sales_contract_reference_provider = SalesContractReferenceProviderFactory(slug="good-provider-slug")
        deposit = DepositFactory(
            ledger=subsidy.ledger,
            desired_deposit_quantity=desired_deposit_quantity,
            sales_contract_reference_id=sales_contract_reference_id,
            sales_contract_reference_provider=sales_contract_reference_provider,
        )

        # Serialize the deposit.
        serializer = DepositSerializer(deposit)
        data = serializer.data

        assert data["uuid"] == str(deposit.uuid)
        assert data["ledger"] == subsidy.ledger.uuid
        assert data["desired_deposit_quantity"] == desired_deposit_quantity
        assert data["transaction"] == deposit.transaction.uuid
        assert data["sales_contract_reference_id"] == sales_contract_reference_id
        assert data["sales_contract_reference_provider"] == (
            "good-provider-slug"
            if set_sales_contract_reference_provider
            else None
        )
