"""
Tests for views.
"""
import os
import urllib
import uuid
from functools import partial
from unittest import mock

import ddt
from django.core.exceptions import MultipleObjectsReturned
from openedx_ledger.models import Transaction, TransactionStateChoices, UnitChoices
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    TransactionFactory
)
from requests.exceptions import HTTPError
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_subsidy.apps.api.v1.tests.mixins import STATIC_ENTERPRISE_UUID, STATIC_LMS_USER_ID, APITestMixin
from enterprise_subsidy.apps.subsidy.models import RevenueCategoryChoices
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory
from test_utils.utils import MockResponse

SERIALIZED_DATE_PATTERN = '%Y-%m-%dT%H:%M:%S.%fZ'


class APITestBase(APITestMixin):
    """
    Provides shared test resource setup between curation-related API test classes.

    Contains boilerplate to create a couple of subsidies with related ledgers and starting transactions.
    """

    enterprise_1_uuid = STATIC_ENTERPRISE_UUID
    enterprise_2_uuid = str(uuid.uuid4())
    subsidy_1_uuid = str(uuid.uuid4())
    subsidy_2_uuid = str(uuid.uuid4())
    subsidy_3_uuid = str(uuid.uuid4())
    subsidy_1_transaction_1_uuid = str(uuid.uuid4())
    subsidy_1_transaction_2_uuid = str(uuid.uuid4())
    subsidy_2_transaction_1_uuid = str(uuid.uuid4())
    subsidy_2_transaction_2_uuid = str(uuid.uuid4())
    subsidy_3_transaction_1_uuid = str(uuid.uuid4())
    subsidy_3_transaction_2_uuid = str(uuid.uuid4())
    subsidy_access_policy_1_uuid = str(uuid.uuid4())
    subsidy_access_policy_2_uuid = str(uuid.uuid4())
    content_key_1 = "course-v1:edX+test+course.1"
    content_key_2 = "course-v1:edX+test+course.2"

    def setUp(self):
        super().setUp()

        # Create a subsidy that the test learner, test admin, and test operater should all be able to access.
        self.subsidy_1 = SubsidyFactory.create(
            uuid=self.subsidy_1_uuid,
            enterprise_customer_uuid=self.enterprise_1_uuid,
            starting_balance=15000
        )
        self.subsidy_1_transaction_initial = self.subsidy_1.ledger.transactions.first()
        self.subsidy_1_transaction_1 = TransactionFactory(
            uuid=self.subsidy_1_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,  # This is the only transaction belonging to the requester.
            subsidy_access_policy_uuid=self.subsidy_access_policy_1_uuid,
            content_key=self.content_key_1,
        )
        self.subsidy_1_transaction_2 = TransactionFactory(
            uuid=self.subsidy_1_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
            subsidy_access_policy_uuid=self.subsidy_access_policy_2_uuid,
            content_key=self.content_key_2,
        )

        # Create an extra subsidy with the same enterprise_customer_uuid, but the learner does not have any transactions
        # in this one.
        self.subsidy_2 = SubsidyFactory.create(
            uuid=self.subsidy_2_uuid,
            enterprise_customer_uuid=self.enterprise_1_uuid,
            starting_balance=15000
        )
        self.subsidy_2_transaction_initial = self.subsidy_2.ledger.transactions.first()
        TransactionFactory(
            uuid=self.subsidy_2_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_2.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )
        TransactionFactory(
            uuid=self.subsidy_2_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_2.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )

        # Create third subsidy with a different enterprise_customer_uuid.  Neither test learner nor the test admin
        # should be able to access this one.  Only the operator should have privileges.
        self.subsidy_3 = SubsidyFactory(
            uuid=self.subsidy_3_uuid,
            enterprise_customer_uuid=self.enterprise_2_uuid,
            starting_balance=15000
        )
        self.subsidy_3_transaction_initial = self.subsidy_3.ledger.transactions.first()
        TransactionFactory(
            uuid=self.subsidy_3_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_3.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )
        TransactionFactory(
            uuid=self.subsidy_3_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_3.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )

        self.all_initial_transactions = set([
            str(self.subsidy_1_transaction_initial.uuid),
            str(self.subsidy_2_transaction_initial.uuid),
            str(self.subsidy_3_transaction_initial.uuid),
        ])


@ddt.ddt
class SubsidyViewSetTests(APITestBase):
    """
    Test SubsidyViewSet.
    """
    get_details_url = partial(reverse, "api:v1:subsidy-detail")
    get_list_url = reverse("api:v1:subsidy-list")
    get_can_redeem_url = partial(reverse, "api:v1:subsidy-can-redeem")

    def test_get_one_subsidy(self):
        """
        Test that a subsidy detail call returns the expected
        serialized response.
        """
        self.set_up_admin(enterprise_uuids=[self.subsidy_1.enterprise_customer_uuid])
        response = self.client.get(self.get_details_url([self.subsidy_1.uuid]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_result = {
            "uuid": str(self.subsidy_1.uuid),
            "title": self.subsidy_1.title,
            "enterprise_customer_uuid": self.subsidy_1.enterprise_customer_uuid,
            "active_datetime": self.subsidy_1.active_datetime.strftime(SERIALIZED_DATE_PATTERN),
            "expiration_datetime": self.subsidy_1.expiration_datetime.strftime(SERIALIZED_DATE_PATTERN),
            "unit": self.subsidy_1.unit,
            "reference_id": self.subsidy_1.reference_id,
            "reference_type": self.subsidy_1.reference_type,
            "current_balance": self.subsidy_1.current_balance(),
            "starting_balance": self.subsidy_1.starting_balance,
            "internal_only": False,
            "revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
        }
        self.assertEqual(expected_result, response.json())

    def test_get_one_subsidy_learner_not_allowed(self):
        """
        Test that learner roles do not allow access to read subsidies.
        """
        self.set_up_learner()
        response = self.client.get(self.get_details_url([self.subsidy_1.uuid]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @ddt.data(
        {'lms_user_id': '', 'content_key': ''},
        {'lms_user_id': 123, 'content_key': ''},
        {'lms_user_id': '', 'content_key': 'some-content-key'},
    )
    def test_can_redeem_bad_request(self, query_params):
        """
        Tests that client receives a 400 status code if either of the required
        query parameters are missing.
        """
        self.set_up_admin(enterprise_uuids=[self.subsidy_1.enterprise_customer_uuid])

        response = self.client.get(
            self.get_can_redeem_url([self.subsidy_1.uuid]),
            data=query_params,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('enterprise_subsidy.apps.api.v1.views.subsidy.can_redeem')
    @ddt.data(False, True)
    def test_can_redeem_happy_path(self, has_existing_transaction, mock_can_redeem):
        """
        Tests that the result of ``api.can_redeem()`` is returned as the response
        payload for a POST to the can_redeem action, including any relevant
        existing transaction.
        """
        self.set_up_admin(enterprise_uuids=[self.subsidy_1.enterprise_customer_uuid])
        expected_redeemable = True
        expected_price = 350
        existing_transaction = None
        if has_existing_transaction:
            existing_transaction = self.subsidy_1_transaction_1
        mock_can_redeem.return_value = (expected_redeemable, expected_price, existing_transaction)
        query_params = {'lms_user_id': 32, 'content_key': 'some-content-key'}

        response = self.client.get(
            self.get_can_redeem_url([self.subsidy_1.uuid]),
            data=query_params,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        expected_existing_transaction = None
        if has_existing_transaction:
            expected_existing_transaction = {
                'created': self.subsidy_1_transaction_1.created.strftime(SERIALIZED_DATE_PATTERN),
                'idempotency_key': str(self.subsidy_1_transaction_1.idempotency_key),
                'metadata': None,
                'modified': self.subsidy_1_transaction_1.modified.strftime(SERIALIZED_DATE_PATTERN),
                'uuid': str(self.subsidy_1_transaction_1_uuid),
                'fulfillment_identifier': None,
                'reversal': None,
                'unit': self.subsidy_1.unit,
                'state': TransactionStateChoices.COMMITTED,
                'quantity': -1000,
                'lms_user_id': STATIC_LMS_USER_ID,
                'subsidy_access_policy_uuid': str(self.subsidy_access_policy_1_uuid),
                'content_key': self.content_key_1,
                'external_reference': [],
            }

        expected_response_data = {
            'can_redeem': expected_redeemable,
            'content_price': expected_price,
            'unit': self.subsidy_1.unit,
            'existing_transaction': expected_existing_transaction,
        }
        self.assertEqual(response.json(), expected_response_data)

    @ddt.data(
            ('operator', status.HTTP_201_CREATED),
            ('learner', status.HTTP_403_FORBIDDEN),
            ('admin', status.HTTP_403_FORBIDDEN),
    )
    @ddt.unpack
    def test_create_new_subsidy_with_permissions(self, role, status_code):
        if role == "admin":
            self.set_up_admin()
        elif role == "learner":
            self.set_up_learner()
        elif role == "operator":
            self.set_up_operator()
        url = self.get_list_url
        data = {
            "reference_id": "aksdkjtkwekwl88890",
            "default_title": "title",
            "default_enterprise_customer_uuid": str(uuid.uuid4()),
            "default_unit": UnitChoices.USD_CENTS,
            "default_starting_balance": "10000",
            "default_revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
            "default_internal_only": True,
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status_code)

    def test_create_subsidy_when_subsidy_exists(self):
        self.set_up_operator()
        url = self.get_list_url
        data_with_existing_reference_id = {
            "reference_id": self.subsidy_1.reference_id,
            "default_title": "title",
            "default_enterprise_customer_uuid": str(uuid.uuid4()),
            "default_unit": UnitChoices.USD_CENTS,
            "default_starting_balance": "10000",
            "default_revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
            "default_internal_only": True,
        }
        response = self.client.post(url, data_with_existing_reference_id, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_new_subsidy_invalid_data(self):
        self.set_up_operator()
        url = self.get_list_url
        data = {
            "reference_id": "",
            "default_title": "title",
            "default_enterprise_customer_uuid": str(uuid.uuid4()),
            "default_unit": UnitChoices.USD_CENTS,
            "default_starting_balance": "10000",
            "default_revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
            "default_internal_only": True,
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual(response.json(), {
            "reference_id": ["This field may not be blank."]
        })

    @ddt.data(
            ('operator', status.HTTP_204_NO_CONTENT),
            ('learner', status.HTTP_403_FORBIDDEN),
            ('admin', status.HTTP_403_FORBIDDEN),
    )
    @ddt.unpack
    def test_valid_delete_subsidy_by_role(self, role, status_code):
        if role == "admin":
            self.set_up_admin()
        elif role == "learner":
            self.set_up_learner()
        elif role == "operator":
            self.set_up_operator()
        response = self.client.delete(self.get_details_url([self.subsidy_1.uuid]))

        self.assertEqual(response.status_code, status_code)

    def test_delete_subsidy_with_invalid_uuid(self):
        self.set_up_operator()
        response = self.client.delete(self.get_details_url([str(uuid.uuid4())]))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertDictEqual(response.json(), {
            'detail': 'MISSING: subsidy.can_write_subsidies'
        })

    @mock.patch('enterprise_subsidy.apps.api.v1.views.subsidy.get_or_create_learner_credit_subsidy')
    def test_create_new_subsidy_unexpected_error(self, mock_get_or_create):
        self.set_up_operator()
        mock_get_or_create.side_effect = Exception("Unexpected error")

        url = self.get_list_url
        data = {
            "reference_id": "aksdkjtkwekwl88890",
            "default_title": "title",
            "default_enterprise_customer_uuid": str(uuid.uuid4()),
            "default_unit": UnitChoices.USD_CENTS,
            "default_starting_balance": "10000",
            "default_revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
            "default_internal_only": True,
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertDictEqual(response.json(), {'detail': 'Subsidy could not be created: Unexpected error'})

    @mock.patch('enterprise_subsidy.apps.api.v1.views.subsidy.get_or_create_learner_credit_subsidy')
    def test_create_new_subsidy_multiple_objects_returned(self, mock_get_or_create):
        self.set_up_operator()
        mock_get_or_create.side_effect = MultipleObjectsReturned("Multiple objects returned")

        url = self.get_list_url
        data = {
            "reference_id": "aksdkjtkwekwl88890",
            "default_title": "title",
            "default_enterprise_customer_uuid": str(uuid.uuid4()),
            "default_unit": UnitChoices.USD_CENTS,
            "default_starting_balance": "10000",
            "default_revenue_category": RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
            "default_internal_only": True,
        }

        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertDictEqual(response.json(), {'detail': "Multiple subsidies with given reference_id found."})


@ddt.ddt
class TransactionViewSetTests(APITestBase):
    """
    Test TransactionViewSet.
    """

    @ddt.data(
        # Test that a subsidy_uuid query parameter is actually required.
        {
            "role": "operator",
            "request_query_params": {},
            "expected_response_status": 400,
            "expected_response_uuids": [],
        },
        # Test that an operator with all access can list every transaction across all enterprise customers.
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_2_transaction_1_uuid,
                APITestBase.subsidy_2_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_3_transaction_1_uuid,
                APITestBase.subsidy_3_transaction_2_uuid,
            ],
        },
        # Test that an enterprise admin can only list transactions within their enterprise.
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_2_transaction_1_uuid,
                APITestBase.subsidy_2_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [],
        },
        # Test that a learner can only list their own transaction.
        {
            "role": "learner",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
            ],
        },
        # Test that a learner can't list other learners' transactions in a different subsidy, but part of the same
        # enterprise customer.
        {
            "role": "learner",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [],
        },
        # Test that an operator with all access can list every transaction across all requested enterprise customers.
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_2_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_2_transaction_1_uuid,
                APITestBase.subsidy_2_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_3_transaction_1_uuid,
                APITestBase.subsidy_3_transaction_2_uuid,
            ],
        },
        # Test that an enterprise admin can list transactions within their enterprise (also provided as a query param).
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
            ],
        },
        # continued...
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_2_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_2_transaction_1_uuid,
                APITestBase.subsidy_2_transaction_2_uuid,
            ],
        },
        # Test that a learner can only list their own transaction (also with enterprise_customer_uuid provided).
        {
            "role": "learner",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_1_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
            ],
        },
        # Test that an operator with all access can list every transaction across enterprise customer number 2.
        {
            "role": "operator",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.subsidy_3_transaction_1_uuid,
                APITestBase.subsidy_3_transaction_2_uuid,
            ],
        },
        # Test that an enterprise admin cannot list transactions outside their enterprise.
        {
            "role": "admin",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [],
        },
        # Test that learner cannot list transactions outside their enterprise.
        {
            "role": "learner",
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_3_uuid,
                "enterprise_customer_uuid": APITestBase.enterprise_2_uuid,
            },
            "expected_response_status": 200,
            "expected_response_uuids": [],
        },
    )
    @ddt.unpack
    def test_list_access(self, role, request_query_params, expected_response_status, expected_response_uuids):
        """
        Test list Transactions permissions.
        """
        if role == "admin":
            self.set_up_admin()
        elif role == "learner":
            self.set_up_learner()
        elif role == "operator":
            self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        query_string = urllib.parse.urlencode(request_query_params)
        if query_string:
            query_string = "?" + query_string
        response = self.client.get(url + query_string)
        assert response.status_code == expected_response_status
        if response.status_code < 300:
            list_response_data = response.json()["results"]
            response_uuids = [tx["uuid"] for tx in list_response_data]
            assert (
                set(response_uuids) - self.all_initial_transactions ==
                set(expected_response_uuids) - self.all_initial_transactions
            )

    @ddt.data(
        # Test that the transaction subsidy_1_transaction_1_uuid is found via subsidy_access_policy_uuid filtering.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "subsidy_access_policy_uuid": APITestBase.subsidy_access_policy_1_uuid,
            },
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,  # This transaction has the first test access policy on it.
            ],
        },
        # Perform the same test as above, but look for a different transaction in the same subsidy.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "subsidy_access_policy_uuid": APITestBase.subsidy_access_policy_2_uuid,
            },
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_2_uuid,  # This transaction has the second test access policy on it.
            ],
        },
        # Perform the same test as above, but look for a non-existent access_policy_uuid.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "subsidy_access_policy_uuid": str(uuid.uuid4()),
            },
            "expected_response_uuids": [],
        },
        # Test filtering by content_key.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "content_key": APITestBase.content_key_1,
            },
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,  # This transaction has the first test content_key on it.
            ],
        },
        # Perform the same test as above, but look for the second course.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "content_key": APITestBase.content_key_2,
            },
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_2_uuid,  # This transaction has the second test content_key on it.
            ],
        },
        # Perform the same test as above, but look for a non-existent course.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "content_key": "course-v1:does+not+exist",
            },
            "expected_response_uuids": [],
        },
        # Test filtering by learner_id.
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "learner_id": STATIC_LMS_USER_ID,
            },
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
            ],
        },
        # Perform the same test as above, but look for a non-existent user
        {
            "request_query_params": {
                "subsidy_uuid": APITestBase.subsidy_1_uuid,
                "learner_id": -1,
            },
            "expected_response_uuids": [],
        },
    )
    @ddt.unpack
    def test_list_filtering(self, request_query_params, expected_response_uuids):
        """
        Test list Transactions works with query parameter filtering.
        """
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        query_string = urllib.parse.urlencode(request_query_params)
        if query_string:
            query_string = "?" + query_string
        response = self.client.get(url + query_string)
        assert response.status_code == status.HTTP_200_OK
        list_response_data = response.json()["results"]
        response_uuids = [tx["uuid"] for tx in list_response_data]
        assert (
            set(response_uuids) - self.all_initial_transactions ==
            set(expected_response_uuids) - self.all_initial_transactions
        )

    def test_list_no_include_aggregates(self):
        """
        Test list() Transactions without include_aggregates flag.
        """
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        request_query_params = {"subsidy_uuid": APITestBase.subsidy_1_uuid}
        query_string = urllib.parse.urlencode(request_query_params)
        response = self.client.get(url + "?" + query_string)
        assert response.status_code == status.HTTP_200_OK
        assert "aggregates" not in response.json()

    def test_list_include_aggregates(self):
        """
        Test list() Transactions include_aggregates flag.
        """
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        request_query_params = {
            "subsidy_uuid": APITestBase.subsidy_1_uuid,
            "include_aggregates": "true",
            "content_key": APITestBase.content_key_1,
        }
        query_string = urllib.parse.urlencode(request_query_params)
        response = self.client.get(url + "?" + query_string)
        assert response.status_code == status.HTTP_200_OK
        list_response_aggregates = response.json()["aggregates"]
        assert list_response_aggregates["total_quantity"] == self.subsidy_1_transaction_1.quantity
        assert list_response_aggregates["unit"] == self.subsidy_1.unit
        assert list_response_aggregates["remaining_subsidy_balance"] == self.subsidy_1.current_balance()

    @ddt.data(
        # Test that an operator with all access can retrieve a random transaction.
        {
            "role": "operator",
            "request_pk": APITestBase.subsidy_1_transaction_2_uuid,
            "expected_response_status": 200,
            "expected_response_uuid": APITestBase.subsidy_1_transaction_2_uuid,
        },
        # Test that an enterprise admin can retrieve a random transaction in their enterprise.
        {
            "role": "admin",
            "request_pk": APITestBase.subsidy_1_transaction_2_uuid,
            "expected_response_status": 200,
            "expected_response_uuid": APITestBase.subsidy_1_transaction_2_uuid,
        },
        # Test that an enterprise admin can't retrieve a transaction not in their enterprise.
        {
            "role": "admin",
            "request_pk": APITestBase.subsidy_3_transaction_1_uuid,
            "expected_response_status": 403,
            "expected_response_uuid": None,
        },
        # Test that a learner can retrieve their own transaction.
        {
            "role": "learner",
            "request_pk": APITestBase.subsidy_1_transaction_1_uuid,
            "expected_response_status": 200,
            "expected_response_uuid": APITestBase.subsidy_1_transaction_1_uuid,
        },
        # Test that a learner can't retrieve somebody else's transaction in the same subsidy.
        {
            "role": "learner",
            "request_pk": APITestBase.subsidy_1_transaction_2_uuid,
            "expected_response_status": 404,
            "expected_response_uuid": None,
        },
        # Test that a learner can't retrieve somebody else's transaction in the a different subsidy.
        {
            "role": "learner",
            "request_pk": APITestBase.subsidy_2_transaction_1_uuid,
            "expected_response_status": 404,
            "expected_response_uuid": None,
        },
    )
    @ddt.unpack
    def test_retrieve_access(self, role, request_pk, expected_response_status, expected_response_uuid):
        """
        Test retrieve Transactions permissions.
        """
        if role == "admin":
            self.set_up_admin()
        elif role == "learner":
            self.set_up_learner()
        elif role == "operator":
            self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        response = self.client.get(os.path.join(url, request_pk + "/"))
        assert response.status_code == expected_response_status
        if response.status_code < 300:
            assert response.json()["uuid"] == expected_response_uuid

    def test_retrieve_invalid_uuid(self):
        """
        Test that providing an invalid transaction UUID throws a 400.
        """
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        request_pk = "invalid-uuid"
        response = self.client.get(os.path.join(url, request_pk + "/"))
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {"detail": "invalid-uuid is not a valid uuid."}

    # Uncomment this later once we have segment events firing.
    # @mock.patch('enterprise_subsidy.apps.api.v1.event_utils.track_event')
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    def test_create(self, mock_price_for_content, mock_enterprise_client):
        """
        Test create Transaction, happy case.
        """
        url = reverse("api:v1:transaction-list")
        test_enroll_enterprise_fulfillment_uuid = "test-enroll-reference-id"
        mock_enterprise_client.enroll.return_value = test_enroll_enterprise_fulfillment_uuid
        mock_price_for_content.return_value = 10000
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_201_CREATED
        create_response_data = response.json()
        assert len(create_response_data["uuid"]) == 36
        # TODO: make this assertion more specific once we hookup the idempotency_key to the request body.
        assert create_response_data["idempotency_key"]
        assert create_response_data["content_key"] == post_data["content_key"]
        assert create_response_data["lms_user_id"] == post_data["learner_id"]
        assert create_response_data["subsidy_access_policy_uuid"] == post_data["subsidy_access_policy_uuid"]
        self.assertDictEqual(create_response_data["metadata"], {})
        assert create_response_data["unit"] == self.subsidy_1.ledger.unit
        assert create_response_data["quantity"] < 0  # No need to be exact at this time, I'm just testing create works.
        assert create_response_data["fulfillment_identifier"] == test_enroll_enterprise_fulfillment_uuid
        assert create_response_data["reversal"] is None
        assert create_response_data["state"] == TransactionStateChoices.COMMITTED

        # `create` was successful, so now call `retreive` to read the new Transaction and do a basic smoke test.
        detail_url = reverse("api:v1:transaction-detail", kwargs={"uuid": create_response_data["uuid"]})
        retrieve_response = self.client.get(detail_url)
        assert retrieve_response.status_code == status.HTTP_200_OK
        retrieve_response_data = retrieve_response.json()
        assert retrieve_response_data["uuid"] == create_response_data["uuid"]
        assert retrieve_response_data["idempotency_key"] == create_response_data["idempotency_key"]

        # Uncomment after Segment events are setup:
        #
        # Finally, check that a tracking event was emitted:
        # mock_track_event.assert_called_once_with(
        #     STATIC_LMS_USER_ID,
        #     SegmentEvents.TRANSACTION_CREATED,
        #     {
        #         "ledger_transaction_uuid": create_response_data["uuid"],
        #         "enterprise_customer_uuid": str(self.subsidy_1.enterprise_customer_uuid),
        #         "subsidy_uuid": str(self.curation_config_one.uuid),
        #     },
        # )

    # Uncomment this later once we have segment events firing.
    # @mock.patch('enterprise_subsidy.apps.api.v1.event_utils.track_event')
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    def test_create_with_metadata(self, mock_price_for_content, mock_enterprise_client):
        """
        Test create Transaction, happy case.
        """
        url = reverse("api:v1:transaction-list")
        test_enroll_enterprise_fulfillment_uuid = "test-enroll-reference-id"
        mock_enterprise_client.enroll.return_value = test_enroll_enterprise_fulfillment_uuid
        mock_price_for_content.return_value = 10000
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        tx_metadata = {
                "geag_first_name": "Donny",
                "geag_last_name": "Kerabatsos",
            }
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
            "metadata": tx_metadata
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_201_CREATED
        create_response_data = response.json()
        assert len(create_response_data["uuid"]) == 36
        # TODO: make this assertion more specific once we hookup the idempotency_key to the request body.
        assert create_response_data["idempotency_key"]
        assert create_response_data["content_key"] == post_data["content_key"]
        assert create_response_data["lms_user_id"] == post_data["learner_id"]
        assert create_response_data["subsidy_access_policy_uuid"] == post_data["subsidy_access_policy_uuid"]
        self.assertDictEqual(create_response_data["metadata"], tx_metadata)
        assert create_response_data["unit"] == self.subsidy_1.ledger.unit
        assert create_response_data["quantity"] < 0  # No need to be exact at this time, I'm just testing create works.
        assert create_response_data["fulfillment_identifier"] == test_enroll_enterprise_fulfillment_uuid
        assert create_response_data["reversal"] is None
        assert create_response_data["state"] == TransactionStateChoices.COMMITTED

        # `create` was successful, so now call `retreive` to read the new Transaction and do a basic smoke test.
        detail_url = reverse("api:v1:transaction-detail", kwargs={"uuid": create_response_data["uuid"]})
        retrieve_response = self.client.get(detail_url)
        assert retrieve_response.status_code == status.HTTP_200_OK
        retrieve_response_data = retrieve_response.json()
        assert retrieve_response_data["uuid"] == create_response_data["uuid"]
        assert retrieve_response_data["idempotency_key"] == create_response_data["idempotency_key"]

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    def test_create_ledger_locked(self, mock_price_for_content, mock_enterprise_client):
        """
        Test create Transaction, 429 response due to the ledger being locked.
        """
        url = reverse("api:v1:transaction-list")
        test_enroll_enterprise_fulfillment_uuid = "test-enroll-reference-id"
        mock_enterprise_client.enroll.return_value = test_enroll_enterprise_fulfillment_uuid
        mock_price_for_content.return_value = 10000
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        self.subsidy_1.ledger.acquire_lock()
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.json() == {"Error": "Attempt to lock the Ledger failed, please try again."}
        self.subsidy_1.ledger.release_lock()

    @ddt.data("admin", "learner")
    def test_create_denied_role(self, role):
        """
        Test create Transaction, permission denied due to not being an operator.
        """
        if role == "admin":
            self.set_up_admin()
        elif role == "learner":
            self.set_up_learner()
        url = reverse("api:v1:transaction-list")
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # Just make sure there's any parseable json which is likely to contain an explanation of the error.
        assert response.json()

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    def test_create_too_expensive(self, mock_price_for_content):
        """
        Test create Transaction, 422 response due to the content price being greater than the stored value.
        """
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        mock_price_for_content.return_value = 10000000  # Wow! that's pricey!
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json() == {"Error": "The given content_key is not currently redeemable for the given subsidy."}

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.content_metadata_api")
    def test_create_content_not_in_catalog(self, mock_content_metadata_api):
        """
        Test create Transaction, 422 response due to the content not existing in any catalog of the enterprise customer.
        """
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        mock_content_metadata_api().get_course_price.side_effect = HTTPError(
            response=MockResponse(None, status.HTTP_404_NOT_FOUND),
        )
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json() == {"Error": "The given content_key is not in any catalog for this customer."}

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.content_metadata_api")
    def test_create_external_enroll_failed(self, mock_content_metadata_api, mock_enterprise_client):
        """
        Test create Transaction, 5xx response due to the external enrollment failing. Check that a transaction is
        created, then rolled back to "failed" state.
        """
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        url = reverse("api:v1:transaction-list")
        mock_enterprise_client.enroll.side_effect = HTTPError()
        mock_content_metadata_api().get_course_price.return_value = 100
        test_content_key = "course-v1:edX+test+course.enroll.failed"
        test_lms_user_id = 1234
        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": test_lms_user_id,
            "content_key": test_content_key,
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        with self.assertRaises(HTTPError):
            self.client.post(url, post_data)
        rolled_back_tx = Transaction.objects.filter(lms_user_id=test_lms_user_id, content_key=test_content_key).first()
        assert rolled_back_tx.state == TransactionStateChoices.FAILED

    def test_create_invalid_subsidy_uuid(self):
        """
        Test create Transaction, failed due to invalid subsidy UUID.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid) + "a",  # Make uuid invalid.
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "detail" in response.json()

    def test_create_invalid_access_policy_uuid(self):
        """
        Test create Transaction, failed due to invalid subsidy access policy UUID.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()) + "a",  # Make uuid invalid.
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Error" in response.json()

    @ddt.data("subsidy_uuid", "learner_id", "content_key", "subsidy_access_policy_uuid")
    def test_create_missing_inputs(self, missing_post_arg):
        """
        Test create Transaction, 4xx due to missing inputs.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_1.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "subsidy_access_policy_uuid": str(uuid.uuid4()),
        }
        del post_data[missing_post_arg]
        response = self.client.post(url, post_data)
        assert response.status_code >= 400 and response.status_code < 500
        # Just make sure there's any parseable json which is likely to contain an explanation of the error.
        assert response.json()

    def test_fetch_transaction_with_external_reference(self):
        """
        Test fetching a Transaction with external reference.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        external_reference_id = "foobar"
        ExternalFulfillmentProviderFactory()
        transaction_with_external_reference = TransactionFactory(
            quantity=-1000,
            ledger=self.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,  # This is the only transaction belonging to the requester.
            subsidy_access_policy_uuid=self.subsidy_access_policy_1_uuid,
            content_key=self.content_key_1,
        )
        ExternalTransactionReferenceFactory(
            external_reference_id=external_reference_id,
            transaction=transaction_with_external_reference,
        )
        url = reverse("api:v1:transaction-list")
        response = self.client.get(os.path.join(url, str(transaction_with_external_reference.uuid) + "/"))
        assert response.json().get('external_reference') == [external_reference_id]


@ddt.ddt
class ContentMetadataViewSetTests(APITestBase):
    """
    Test ContentMetadataViewSet.
    """
    content_uuid_1 = str(uuid.uuid4())
    content_key_1 = "edX+DemoX"
    content_uuid_2 = str(uuid.uuid4())
    content_key_2 = "edX+DemoX2"
    edx_course_metadata = {
        "key": content_key_1,
        "content_type": "course",
        "uuid": content_uuid_1,
        "title": "Demonstration Course",
        "entitlements": [
            {
                "mode": "verified",
                "price": "149.00",
                "currency": "USD",
                "sku": "8A47F9E",
                "expires": "null"
            }
        ],
        "product_source": None,
    }
    executive_education_course_metadata = {
        "key": content_key_2,
        "content_type": "course",
        "uuid": content_uuid_2,
        "title": "Demonstration Course",
        "entitlements": [
            {
                "mode": "paid-executive-education",
                "price": "599.49",
                "currency": "USD",
                "sku": "B98DE21",
                "expires": "null"
            }
        ],
        "product_source": {
            "name": "2u",
            "slug": "2u",
            "description": "2U, Trilogy, Getsmarter -- external source for 2u courses and programs"
        },
        "additional_metadata": {
            "variant_id": "79a95406-a9ac-49b3-a27c-44f3fd06092e"
        }
    }
    mock_http_error_reason = 'Something Went Wrong'
    mock_http_error_url = 'foobar.com'

    @ddt.data(
        {
            'expected_content_uuid': content_uuid_1,
            'expected_content_key': content_key_1,
            'expected_content_price': 14900.0,
            'mock_metadata': edx_course_metadata,
            'expected_source': 'edX',
            'expected_mode': 'verified',
            'expected_geag_variant_id': None,
        },
        {
            'expected_content_uuid': content_uuid_2,
            'expected_content_key': content_key_2,
            'expected_content_price': 59949,
            'mock_metadata': executive_education_course_metadata,
            'expected_source': '2u',
            'expected_mode': 'paid-executive-education',
            # generated randomly using a fair die
            'expected_geag_variant_id': '79a95406-a9ac-49b3-a27c-44f3fd06092e',
        },
    )
    @ddt.unpack
    def test_successful_get(
        self,
        expected_content_uuid,
        expected_content_key,
        expected_content_price,
        mock_metadata,
        expected_source,
        expected_mode,
        expected_geag_variant_id,
    ):
        with mock.patch(
            'enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient',
            return_value=mock.MagicMock()
        ) as mock_oauth_client:
            customer_uuid = uuid.uuid4()
            self.set_up_admin(enterprise_uuids=[str(customer_uuid)])
            mock_oauth_client.return_value.get.return_value = MockResponse(mock_metadata, 200)
            url = reverse('api:v1:content-metadata', kwargs={'content_identifier': expected_content_key})
            response = self.client.get(url + f'?enterprise_customer_uuid={str(customer_uuid)}')
            assert response.status_code == 200
            assert response.json() == {
                'content_uuid': str(expected_content_uuid),
                'content_key': expected_content_key,
                'source': expected_source,
                'content_price': expected_content_price,
                'mode': expected_mode,
                'geag_variant_id': expected_geag_variant_id,
            }

            # Everything after this line is testing the view's cache
            # If this mock response is ever hit, the test will fail, caching prevents it.
            mock_oauth_client.return_value.get.side_effect = Exception("Does not reach this")
            response = self.client.get(url + f'?enterprise_customer_uuid={str(customer_uuid)}')
            assert response.status_code == 200
            assert response.json() == {
                'content_uuid': str(expected_content_uuid),
                'content_key': expected_content_key,
                'source': expected_source,
                'content_price': expected_content_price,
                'mode': expected_mode,
                'geag_variant_id': expected_geag_variant_id,
            }

    def test_failure_no_permission(self):
        self.set_up_admin(enterprise_uuids=[str(uuid.uuid4())])
        url = reverse('api:v1:content-metadata', kwargs={'content_identifier': self.content_key_1})
        response = self.client.get(url + f'?enterprise_customer_uuid={str(uuid.uuid4())}')
        assert response.status_code == 403
        assert response.json() == {'detail': 'MISSING: subsidy.can_read_metadata'}

    @ddt.data(
        {
            'catalog_status_code': 404,
            'expected_response': 'Content not found',
        },
        {
            'catalog_status_code': 403,
            'expected_response': f'Failed to fetch data from catalog service with exc: '
                                 f'403 Client Error: {mock_http_error_reason} for url: {mock_http_error_url}',
        },
    )
    @ddt.unpack
    def test_failure_exception_while_gather_metadata(self, catalog_status_code, expected_response):
        with mock.patch(
            'enterprise_subsidy.apps.api_client.base_oauth.OAuthAPIClient',
            return_value=mock.MagicMock()
        ) as mock_oauth_client:
            customer_uuid = uuid.uuid4()
            self.set_up_admin(enterprise_uuids=[str(customer_uuid)])
            mock_oauth_client.return_value.get.return_value = MockResponse(
                {"something": "fail"},
                catalog_status_code,
                reason=self.mock_http_error_reason,
                url=self.mock_http_error_url
            )
            url = reverse('api:v1:content-metadata', kwargs={'content_identifier': 'content_key'})
            response = self.client.get(url + f'?enterprise_customer_uuid={str(customer_uuid)}')
            assert response.status_code == catalog_status_code
            assert response.json() == expected_response
