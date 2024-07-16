"""
Tests for the v2 deposit views.
"""
import uuid

import ddt
from openedx_ledger.models import Deposit, SalesContractReferenceProvider
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_subsidy.apps.api.v1.tests.mixins import STATIC_ENTERPRISE_UUID, APITestMixin
from enterprise_subsidy.apps.subsidy.models import SubsidyReferenceChoices
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory

# This test depends on data migration subsidy.0022_backfill_initial_deposits having been run to seed the
# SalesContractReferenceProvider table with a record that has this slug.
DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG = SubsidyReferenceChoices.SALESFORCE_OPPORTUNITY_LINE_ITEM


@ddt.ddt
class DepositCreateViewTests(APITestMixin):
    """
    Test deposit creation via the deposit-admin-create view.
    """

    @ddt.data(
        ###
        # Happy paths:
        ###
        {
            "subsidy_active": True,
            # Typical request we expect to see 99% of the time.
            "creation_request_data": {
                "desired_deposit_quantity": 100,
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG,
                "metadata": {"foo": "bar"},
            },
            "expected_response_status": status.HTTP_201_CREATED,
        },
        {
            "subsidy_active": True,
            # Only the minimal set of required request fields included.
            "creation_request_data": {
                "desired_deposit_quantity": 100,
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG,
            },
            "expected_response_status": status.HTTP_201_CREATED,
        },

        ###
        # Sad paths:
        ###
        {
            "subsidy_active": False,  # Inactive subsidy invalidates request.
            "creation_request_data": {
                "desired_deposit_quantity": 100,
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG,
            },
            "expected_response_status": status.HTTP_422_UNPROCESSABLE_ENTITY,
        },
        {
            "subsidy_active": True,
            "creation_request_data": {
                "desired_deposit_quantity": -100,  # Invalid deposit quantity.
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG,
            },
            "expected_response_status": status.HTTP_400_BAD_REQUEST,
        },
        {
            "subsidy_active": True,
            "creation_request_data": {
                "desired_deposit_quantity": 0,  # Invalid deposit quantity.
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": DEFAULT_SALES_CONTRACT_REFERENCE_PROVIDER_SLUG,
            },
            "expected_response_status": status.HTTP_400_BAD_REQUEST,
        },
        {
            "subsidy_active": True,
            "creation_request_data": {
                "desired_deposit_quantity": 100,
                "sales_contract_reference_id": str(uuid.uuid4()),
                "sales_contract_reference_provider": "totally-invalid-slug",  # Slug doesn't have existing object in db.
            },
            "expected_response_status": status.HTTP_400_BAD_REQUEST,
        },
    )
    @ddt.unpack
    def test_deposit_creation(
        self,
        subsidy_active,
        creation_request_data,
        expected_response_status,
    ):
        """
        Test that the DepositCreationRequestSerializer correctly creates a deposit idempotently OR fails with the
        correct status code.
        """
        self.set_up_operator()

        subsidy = SubsidyFactory(enterprise_customer_uuid=STATIC_ENTERPRISE_UUID)
        if not subsidy_active:
            subsidy.expiration_datetime = subsidy.active_datetime
            subsidy.save()

        url = reverse("api:v2:deposit-admin-create", args=[subsidy.uuid])

        response = self.client.post(url, creation_request_data)
        assert response.status_code == expected_response_status
        if response.status_code < 300:
            assert response.data["ledger"] == subsidy.ledger.uuid
            assert response.data["desired_deposit_quantity"] == creation_request_data["desired_deposit_quantity"]
            assert response.data["sales_contract_reference_id"] == creation_request_data["sales_contract_reference_id"]
            assert response.data["sales_contract_reference_provider"] == \
                creation_request_data["sales_contract_reference_provider"]
            assert Deposit.objects.count() == 2
            created_deposit = Deposit.objects.get(uuid=response.data["uuid"])
            assert created_deposit.transaction.metadata == creation_request_data.get("metadata", {})
        else:
            assert Deposit.objects.count() == 1

        response_x2 = self.client.post(url, creation_request_data)
        if expected_response_status == status.HTTP_201_CREATED:
            assert response_x2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        else:
            assert response_x2.status_code == expected_response_status

    @ddt.data(
        {
            "role": "learner",
            "subsidy_enterprise_uuid": STATIC_ENTERPRISE_UUID,
            "expected_response_status": status.HTTP_403_FORBIDDEN,
        },
        {
            "role": "admin",
            "subsidy_enterprise_uuid": STATIC_ENTERPRISE_UUID,
            "expected_response_status": status.HTTP_403_FORBIDDEN,
        },
        {
            "role": "learner",
            "subsidy_enterprise_uuid": uuid.uuid4(),
            "expected_response_status": status.HTTP_403_FORBIDDEN,
        },
        {
            "role": "admin",
            "subsidy_enterprise_uuid": uuid.uuid4(),
            "expected_response_status": status.HTTP_403_FORBIDDEN,
        },
        {
            "role": "operator",
            "subsidy_enterprise_uuid": uuid.uuid4(),
            "expected_response_status": status.HTTP_201_CREATED,
        },
    )
    @ddt.unpack
    def test_learners_and_admins_cannot_create_deposits(
        self,
        role,
        subsidy_enterprise_uuid,
        expected_response_status,
    ):
        """
        Neither learner nor admin roles should provide the ability to create transactions.
        """
        if role == 'admin':
            self.set_up_admin()
        if role == 'learner':
            self.set_up_learner()
        if role == 'operator':
            self.set_up_operator()

        # Create a subsidy either in or not in the requesting user's enterprise.
        subsidy = SubsidyFactory(enterprise_customer_uuid=subsidy_enterprise_uuid)

        # Construct and make a request that is guaranteed to work if the user's role has correct permissions.
        url = reverse("api:v2:deposit-admin-create", args=[subsidy.uuid])
        creation_request_data = {
            "desired_deposit_quantity": 50,
            "sales_contract_reference_id": "abc123",
            "sales_contract_reference_provider": SalesContractReferenceProvider.objects.first().slug,
            "metadata": {"foo": "bar"},
        }
        response = self.client.post(url, creation_request_data)

        assert response.status_code == expected_response_status
