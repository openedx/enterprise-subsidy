"""
Tests for the v2 transaction views.
"""
import urllib
import uuid
from datetime import timedelta
from unittest import mock

import ddt
from edx_rbac.utils import ALL_ACCESS_CONTEXT
from openedx_ledger.models import LedgerLockAttemptFailed, Transaction, TransactionStateChoices, UnitChoices
from openedx_ledger.test_utils.factories import ReversalFactory, TransactionFactory
from requests.exceptions import HTTPError
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_subsidy.apps.api.exceptions import ErrorCodes
from enterprise_subsidy.apps.api.v1.serializers import TransactionCreationError
from enterprise_subsidy.apps.api.v1.tests.mixins import STATIC_ENTERPRISE_UUID, STATIC_LMS_USER_ID, APITestMixin
from enterprise_subsidy.apps.core.utils import localized_utcnow
from enterprise_subsidy.apps.fulfillment.api import FulfillmentException
from enterprise_subsidy.apps.subsidy.constants import SYSTEM_ENTERPRISE_ADMIN_ROLE, SYSTEM_ENTERPRISE_LEARNER_ROLE
from enterprise_subsidy.apps.subsidy.models import ContentNotFoundForCustomerException
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory

SERIALIZED_DATE_PATTERN = '%Y-%m-%dT%H:%M:%S.%fZ'


class APITestBase(APITestMixin):
    """
    Provides shared test resource setup between curation-related API test classes.

    Contains boilerplate to create a couple of subsidies with related ledgers and starting transactions.
    """

    lms_user_email = 'edx@example.com'
    enterprise_1_uuid = STATIC_ENTERPRISE_UUID
    enterprise_2_uuid = str(uuid.uuid4())
    enterprise_3_uuid = str(uuid.uuid4())

    subsidy_1_uuid = str(uuid.uuid4())
    subsidy_2_uuid = str(uuid.uuid4())
    subsidy_3_uuid = str(uuid.uuid4())
    subsidy_4_uuid = str(uuid.uuid4())

    subsidy_1_transaction_1_uuid = str(uuid.uuid4())
    subsidy_1_transaction_2_uuid = str(uuid.uuid4())
    subsidy_1_transaction_3_uuid = str(uuid.uuid4())
    subsidy_2_transaction_1_uuid = str(uuid.uuid4())
    subsidy_2_transaction_2_uuid = str(uuid.uuid4())
    subsidy_3_transaction_1_uuid = str(uuid.uuid4())
    subsidy_3_transaction_2_uuid = str(uuid.uuid4())
    subsidy_4_transaction_1_uuid = str(uuid.uuid4())
    subsidy_4_transaction_2_uuid = str(uuid.uuid4())
    # Add an extra UUID for any failed transaction that
    # a subclass may need to use
    failed_transaction_uuid = str(uuid.uuid4())

    subsidy_access_policy_1_uuid = str(uuid.uuid4())
    subsidy_access_policy_2_uuid = str(uuid.uuid4())
    subsidy_access_policy_3_uuid = str(uuid.uuid4())

    content_key_1 = "course-v1:edX+test+course.1"
    content_key_2 = "course-v1:edX+test+course.2"
    content_title_1 = "edX: Test Course 1"
    content_title_2 = "edx: Test Course 2"
    transaction_quantity_1 = -1
    transaction_quantity_2 = -2
    failed_content_title = "Studebaker"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_subsidies()
        cls._setup_transactions()

    @classmethod
    def _setup_subsidies(cls):
        # Create a subsidy that the test learner, test admin, and test operater should all be able to access.
        cls.subsidy_1 = SubsidyFactory.create(
            uuid=uuid.UUID(cls.subsidy_1_uuid),
            enterprise_customer_uuid=uuid.UUID(cls.enterprise_1_uuid),
            starting_balance=15000,
        )
        cls.subsidy_1_transaction_initial = cls.subsidy_1.ledger.transactions.first()

        # Create an extra subsidy with the same enterprise_customer_uuid
        cls.subsidy_2 = SubsidyFactory.create(
            uuid=cls.subsidy_2_uuid,
            enterprise_customer_uuid=cls.enterprise_1_uuid,
            starting_balance=15000
        )
        cls.subsidy_2_transaction_initial = cls.subsidy_2.ledger.transactions.first()

        # Create third subsidy with a different enterprise_customer_uuid.
        # Neither test learner nor the test admin should be able to access this one.
        # Only the operator should have privileges.
        cls.subsidy_3 = SubsidyFactory(
            uuid=cls.subsidy_3_uuid,
            enterprise_customer_uuid=cls.enterprise_2_uuid,
            starting_balance=15000
        )
        cls.subsidy_3_transaction_initial = cls.subsidy_3.ledger.transactions.first()

        cls.subsidy_4 = SubsidyFactory(
            uuid=cls.subsidy_4_uuid,
            enterprise_customer_uuid=cls.enterprise_3_uuid,
            starting_balance=15000
        )
        cls.subsidy_4_transaction_initial = cls.subsidy_4.ledger.transactions.first()

    @classmethod
    def _setup_transactions(cls):
        cls.subsidy_1_transaction_1 = TransactionFactory(
            uuid=cls.subsidy_1_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,  # This is the only transaction belonging to the requester.
            subsidy_access_policy_uuid=cls.subsidy_access_policy_1_uuid,
            content_key=cls.content_key_1,
        )
        cls.subsidy_1_transaction_2 = TransactionFactory(
            uuid=cls.subsidy_1_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
            lms_user_email=cls.lms_user_email,
            subsidy_access_policy_uuid=cls.subsidy_access_policy_2_uuid,
            content_key=cls.content_key_2,
            content_title=cls.content_title_2,
        )
        # Also create a reversed transaction, and also include metadata on both the transaction and reversal.
        cls.subsidy_1_transaction_3 = TransactionFactory(
            uuid=cls.subsidy_1_transaction_3_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,
            lms_user_email=cls.lms_user_email,
            subsidy_access_policy_uuid=cls.subsidy_access_policy_2_uuid,
            content_key=cls.content_key_2,
            content_title=cls.content_title_2,
            metadata={"bin": "baz"},
        )
        cls.subsidy_1_transaction_3_reversal = ReversalFactory(
            transaction=cls.subsidy_1_transaction_3,
            state=TransactionStateChoices.COMMITTED,
            quantity=1000,
            metadata={"foo": "bar"},
        )

        # In the extra subsidy with the same enterprise_customer_uuid,
        # the static learner does not have any transactions in this one.
        cls.subsidy_2_transaction_1 = TransactionFactory(
            uuid=cls.subsidy_2_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_2.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )
        cls.subsidy_2_transaction_1 = TransactionFactory(
            uuid=cls.subsidy_2_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_2.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )

        cls.subsidy_3_transaction_1 = TransactionFactory(
            uuid=cls.subsidy_3_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_3.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )
        cls.subsidy_3_transaction_2 = TransactionFactory(
            uuid=cls.subsidy_3_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=cls.subsidy_3.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )

        cls.subsidy_4_transaction_1 = TransactionFactory(
            uuid=cls.subsidy_4_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=cls.transaction_quantity_1,
            ledger=cls.subsidy_4.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )
        cls.subsidy_4_transaction_2 = TransactionFactory(
            uuid=cls.subsidy_4_transaction_2_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=cls.transaction_quantity_2,
            ledger=cls.subsidy_4.ledger,
            lms_user_id=STATIC_LMS_USER_ID+1000,
        )

    def _prepend_initial_transaction_uuid(self, subsidy_uuid, user_transaction_uuids):
        """
        Helper to put the appropriate initial transaction uuid for a subsidy at the start
        of a list.
        """
        if subsidy_uuid == self.subsidy_1_uuid:
            user_transaction_uuids.insert(0, str(self.subsidy_1_transaction_initial.uuid))
        if subsidy_uuid == self.subsidy_2_uuid:
            user_transaction_uuids.insert(0, str(self.subsidy_2_transaction_initial.uuid))
        if subsidy_uuid == self.subsidy_3_uuid:
            user_transaction_uuids.insert(0, str(self.subsidy_3_transaction_initial.uuid))


@ddt.ddt
class TransactionUserListViewTests(APITestBase):
    """
    Test list operations on transactions via the transaction-user-list view.
    """

    @ddt.data(
        # Test that a learner can only list their own transaction.
        {
            "subsidy_uuid": APITestBase.subsidy_1_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_3_uuid,
            ],
        },
        # Test that a learner can't list other learners' transactions in a different subsidy, but part of the same
        # enterprise customer.
        {
            "subsidy_uuid": APITestBase.subsidy_2_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [],
        },
    )
    @ddt.unpack
    def test_list_transactions_happy_path(
        self, subsidy_uuid, expected_response_status, expected_response_uuids
    ):
        """
        Test listing of Transaction records for a user with the learner role.
        """
        self.set_up_learner()
        url = reverse("api:v2:transaction-user-list", args=[subsidy_uuid])

        response = self.client.get(url)

        assert response.status_code == expected_response_status
        list_response_data = response.json()["results"]
        response_uuids = [tx["uuid"] for tx in list_response_data]
        self.assertEqual(response_uuids, expected_response_uuids)

    def test_list_no_permission_for_customer_responds_with_403(self):
        """
        Tests that an authenticated learner without role-based access
        to a given customer gets a 403 when requesting access to transactions therein.
        """
        self.set_up_learner()
        url = reverse("api:v2:transaction-user-list", args=[self.subsidy_3.uuid])

        response = self.client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_no_lms_user_id_responds_with_404(self):
        """
        Tests that an authenticated learner without an inferrable lms_user_id
        gets a 404 response when requesting access to transactions of any customer.
        """
        self.set_up_learner(include_jwt_user_id=False)

        url = reverse("api:v2:transaction-user-list", args=[self.subsidy_1_uuid])

        response = self.client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@ddt.ddt
class TransactionAdminListViewTests(APITestBase):
    """
    Test list operations on transactions via the transaction-admin-list-create view.
    """
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # setup a failed transaction to test our state filtering
        cls.subsidy_1_transaction_1 = TransactionFactory(
            uuid=cls.failed_transaction_uuid,
            state=TransactionStateChoices.FAILED,
            quantity=0,
            ledger=cls.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,  # This is the only transaction belonging to the requester.
            lms_user_email=cls.lms_user_email,
            subsidy_access_policy_uuid=cls.subsidy_access_policy_1_uuid,
            content_key=cls.content_key_1,
            content_title=cls.failed_content_title,
        )

    def test_list_transactions_metadata_format(self):
        """
        Test that the serialized metadata in the response body is well formed.
        """
        self.set_up_operator()
        url = reverse("api:v2:transaction-admin-list-create", args=[APITestBase.subsidy_1_uuid])

        # These query params are designed to return self.subsidy_1_transaction_3
        query_params = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_2,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_2_uuid,
        }
        response = self.client.get(url, data=query_params)

        assert response.status_code == status.HTTP_200_OK
        list_response_data = response.json()["results"]
        assert isinstance(list_response_data[0]["metadata"], dict)
        assert isinstance(list_response_data[0]["reversal"]["metadata"], dict)

    @ddt.data(
        # Test that an admin can list all transactions in a subsidy within their enterprise.
        {
            "role": "admin",
            "subsidy_uuid": APITestBase.subsidy_1_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
                APITestBase.subsidy_1_transaction_3_uuid,
                APITestBase.failed_transaction_uuid,
            ],
        },
        # Test that an admin can list transactions in a different subsidy, but part of the same
        # enterprise customer.
        {
            "role": "admin",
            "subsidy_uuid": APITestBase.subsidy_2_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [
                APITestBase.subsidy_2_transaction_1_uuid,
                APITestBase.subsidy_2_transaction_2_uuid,
            ],
        },
        # Test that an operator can list transactions in any subsidy.
        {
            "role": "operator",
            "subsidy_uuid": APITestBase.subsidy_3_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [
                APITestBase.subsidy_3_transaction_1_uuid,
                APITestBase.subsidy_3_transaction_2_uuid,
            ],
        },

    )
    @ddt.unpack
    def test_admin_list_transactions_happy_path_no_filters(
        self, role, subsidy_uuid, expected_response_status, expected_response_uuids
    ):
        """
        Test listing of Transaction records for an admin or operator.
        """
        if role == 'admin':
            self.set_up_admin()
        if role == 'operator':
            self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[subsidy_uuid])

        response = self.client.get(url)

        assert response.status_code == expected_response_status

        list_response_data = response.json()["results"]
        response_uuids = [tx["uuid"] for tx in list_response_data]
        # admins and operators can see the initial transactions
        # of their subsidies' ledgers.
        self._prepend_initial_transaction_uuid(subsidy_uuid, expected_response_uuids)
        self.assertEqual(sorted(response_uuids), sorted(expected_response_uuids))

    def test_admin_list_transactions_default_pagination_behavior(self):
        """
        Test listing of Transaction records for an admin or operator adheres to edx rest framework default pagination.
        """
        self.set_up_operator()
        subsidy_uuid = APITestBase.subsidy_3_uuid
        url = reverse("api:v2:transaction-admin-list-create", args=[subsidy_uuid])

        response = self.client.get(url)
        assert "num_pages" in response.data.keys()
        assert "count" in response.data.keys()
        assert "current_page" in response.data.keys()
        assert "results" in response.data.keys()

    @ddt.data('admin', 'operator')
    def test_admin_list_transactions_happy_path_with_filters(self, role):
        """
        Test filtering of Transaction records for an admin or operator.
        """
        if role == 'admin':
            self.set_up_admin()
        if role == 'operator':
            self.set_up_operator()

        query_params = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_1,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'state': [TransactionStateChoices.COMMITTED, TransactionStateChoices.FAILED],
            'include_aggregates': 'true',
        }
        query_string = urllib.parse.urlencode(query_params, doseq=True)
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1_uuid])
        url += '?' + query_string

        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        response_json = response.json()
        list_response_data = response_json["results"]
        response_aggregates = response_json['aggregates']
        response_uuids = [tx["uuid"] for tx in list_response_data]
        expected_response_uuids = [
            self.subsidy_1_transaction_1_uuid,
            self.failed_transaction_uuid,
        ]
        self.assertEqual(sorted(response_uuids), sorted(expected_response_uuids))
        self.assertEqual(response_aggregates, {
            'total_quantity': -1000,
            'unit': UnitChoices.USD_CENTS,
            'remaining_subsidy_balance': 13000,
        })

    def test_list_no_permission_for_customer_responds_with_403(self):
        """
        Tests that an authenticated admin without role-based access
        to a given customer gets a 403 when requesting access to transactions therein.
        """
        self.set_up_admin()
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_3.uuid])

        response = self.client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_with_mixed_wildcard_admin_and_learner_access_gets_200(self):
        """
        Test list Transactions permissions as an all-access admin even though they still have an
        enterprise-scoped learner role.
        """
        self.set_up_admin()
        self.set_jwt_cookie([
            (SYSTEM_ENTERPRISE_ADMIN_ROLE, ALL_ACCESS_CONTEXT),
            (SYSTEM_ENTERPRISE_LEARNER_ROLE, self.enterprise_1_uuid),
        ])

        query_params = {
            'state': TransactionStateChoices.COMMITTED,
        }
        query_string = urllib.parse.urlencode(query_params)
        # The all-access admin role assignment should let the admin
        # user read the transactions for subsidy_1
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1_uuid])
        url += '?' + query_string

        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        list_response_data = response.json()["results"]
        response_uuids = [tx["uuid"] for tx in list_response_data]
        expected_response_uuids = [
            APITestBase.subsidy_1_transaction_1_uuid,
            APITestBase.subsidy_1_transaction_2_uuid,
            APITestBase.subsidy_1_transaction_3_uuid,
        ]
        self._prepend_initial_transaction_uuid(self.subsidy_1_uuid, expected_response_uuids)
        self.assertEqual(sorted(response_uuids), sorted(expected_response_uuids))

    def test_learner_cannot_use_admin_list(self):
        """
        Tests that an authenticated learner, even one with role-based access
        to a given customer, gets a 403 when requesting admin list access to transactions therein.
        """
        self.set_up_learner()
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])

        response = self.client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data('admin', 'operator')
    def test_list_no_matching_subsidy_uuid_error_response(self, role):
        """
        Tests that an authenticated admin or operator receives a 403 response
        when requesting a subsidy uuid that does not exist.
        """
        if role == 'admin':
            self.set_up_admin()
        if role == 'operator':
            self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[uuid.uuid4()])

        response = self.client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data(
        {
            "request_subsidy_uuid": APITestBase.subsidy_1_uuid,
            "request_search_query": "edx@example.com",
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.failed_transaction_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
                APITestBase.subsidy_1_transaction_3_uuid,
            ],
        },
        {
            "request_subsidy_uuid": APITestBase.subsidy_1_uuid,
            "request_search_query": APITestBase.failed_content_title,
            "expected_response_status": 200,
            "expected_response_uuids": [
                APITestBase.failed_transaction_uuid,
            ],
        },
    )
    @ddt.unpack
    def test_list_search(
        self,
        request_subsidy_uuid,
        request_search_query,
        expected_response_status,
        expected_response_uuids,
    ):
        """
        Test list Transactions search.
        """
        self.set_up_admin()
        url = reverse("api:v2:transaction-admin-list-create", args=[request_subsidy_uuid])
        query_string = urllib.parse.urlencode({"search": request_search_query})
        if query_string:
            query_string = "?" + query_string
        response = self.client.get(url + query_string)
        assert response.status_code == expected_response_status
        if response.status_code < 300:
            list_response_data = response.json()["results"]
            response_uuids = [tx["uuid"] for tx in list_response_data]
            self.assertEqual(sorted(response_uuids), sorted(expected_response_uuids))

    @ddt.data(
        {
            "request_subsidy_uuid": APITestBase.subsidy_4_uuid,
            "request_ordering_query": "created",
            "expected_response_status": 200,
            "expected_response_uuid_order": [
                APITestBase.subsidy_4_transaction_1_uuid,
                APITestBase.subsidy_4_transaction_2_uuid,
            ],
        },
        {
            "request_subsidy_uuid": APITestBase.subsidy_4_uuid,
            "request_ordering_query": "quantity",
            "expected_response_status": 200,
            "expected_response_uuid_order": [
                APITestBase.subsidy_4_transaction_2_uuid,
                APITestBase.subsidy_4_transaction_1_uuid,
            ],
        },
    )
    @ddt.unpack
    def test_list_ordering(
        self,
        request_subsidy_uuid,
        request_ordering_query,
        expected_response_status,
        expected_response_uuid_order,
    ):
        """
        Test list Transactions search.
        """
        self.set_up_admin(enterprise_uuids=[self.enterprise_3_uuid])
        url = reverse("api:v2:transaction-admin-list-create", args=[request_subsidy_uuid])
        query_string = urllib.parse.urlencode({"ordering": request_ordering_query})
        if query_string:
            query_string = "?" + query_string
        response = self.client.get(url + query_string)
        assert response.status_code == expected_response_status
        if response.status_code < 300:
            list_response_data = response.json()["results"]
            response_uuids = [tx["uuid"] for tx in list_response_data]
            response_uuids.remove(str(self.subsidy_4_transaction_initial.uuid))
            self.assertEqual(response_uuids, expected_response_uuid_order)


@ddt.ddt
class TransactionAdminCreateViewTests(APITestBase):
    """
    Test transaction creation operations via the transaction-admin-list-create view.
    """
    @classmethod
    def setUpClass(cls):
        """
        We only need to setup subsidies for the creation tests.
        """
        APITestMixin.setUpClass()
        cls._setup_subsidies()

    def tearDown(self):
        """
        Deletes any transactions with a non-null lms_user_id (i.e. everything
        except the initializing transactions for the subsidies).
        """
        Transaction.objects.exclude(lms_user_id__isnull=True).delete()

    @ddt.data('learner', 'admin')
    def test_learners_and_admins_cannot_create_transactions(self, role):
        """
        Neither learner or admin roles should provide the ability to create transactions.
        """
        if role == 'admin':
            self.set_up_admin()
        if role == 'learner':
            self.set_up_learner()

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])

        response = self.client.post(url, {'anything': 'goes'})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_operator_creation_with_no_matching_subsidy_uuid_gets_403(self):
        """
        Tests that an authenticated operator receives a 403 response
        when creating in a subsidy uuid that does not exist.
        """
        self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[uuid.uuid4()])
        creation_request_payload = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_2,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
        }

        response = self.client.post(url, creation_request_payload)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @ddt.data(
        # check case where subsidy is only active in future
        {
            'active_datetime': localized_utcnow() + timedelta(days=1),
            'expiration_datetime': localized_utcnow() + timedelta(days=10),
        },
        # check case where subsidy has expired
        {
            'active_datetime': localized_utcnow() - timedelta(days=10),
            'expiration_datetime': localized_utcnow() - timedelta(days=1),
        },
    )
    @ddt.unpack
    def test_operator_creation_with_inactive_subsidy_gets_422(self, active_datetime, expiration_datetime):
        """
        Tests that an authenticated operator receives a 422 response
        when attempting to create a transaction in an inactive subsidy uuid.
        """
        self.set_up_operator()
        inactive_subsidy = SubsidyFactory.create(
            uuid=uuid.uuid4(),
            enterprise_customer_uuid=uuid.UUID(self.enterprise_1_uuid),
            starting_balance=15000,
            active_datetime=active_datetime,
            expiration_datetime=expiration_datetime,
        )

        url = reverse("api:v2:transaction-admin-list-create", args=[inactive_subsidy.uuid])
        creation_request_payload = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_2,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
        }

        response = self.client.post(url, creation_request_payload)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json() == {
            'detail': 'Cannot create a transaction in an inactive subsidy',
            'code': ErrorCodes.INACTIVE_SUBSIDY_CREATION_ERROR,
        }

    def test_operator_creation_with_lock_failure_gets_429(self):
        """
        Tests that an authenticated operator receives a 429 response
        when creation leads to a LedgerLockAttemptFailed exception.
        """
        self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        creation_request_payload = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_2,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
        }

        with mock.patch(
            'enterprise_subsidy.apps.subsidy.models.Subsidy.redeem',
            side_effect=LedgerLockAttemptFailed,
            autospec=True,
        ) as mocked_redeem:
            response = self.client.post(url, creation_request_payload)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        mocked_redeem.assert_called_once_with(
            self.subsidy_1,  # redeem is a bound method, but we have to patch via the module.
            STATIC_LMS_USER_ID,
            self.content_key_2,
            uuid.UUID(self.subsidy_access_policy_1_uuid),
            idempotency_key='my-idempotency-key',
            requested_price_cents=None,
            metadata=None,
        )
        assert response.json() == {'detail': 'Attempt to lock the Ledger failed, please try again.'}

    @ddt.data(
        {
            'exception_to_raise': HTTPError('Error from the enrollment API'),
            'expected_error_code': ErrorCodes.ENROLLMENT_ERROR,
        },
        {
            'exception_to_raise': ContentNotFoundForCustomerException('No ticket'),
            'expected_error_code': ErrorCodes.CONTENT_NOT_FOUND,
        },
        {
            'exception_to_raise': Exception('Other error'),
            'expected_error_code': ErrorCodes.TRANSACTION_CREATION_ERROR,
        },
        {
            'exception_to_raise': FulfillmentException('Fulfillment failure'),
            'expected_error_code': ErrorCodes.FULFILLMENT_ERROR,
        },
    )
    @ddt.unpack
    def test_operator_creation_expected_422_errors(self, exception_to_raise, expected_error_code):
        """
        Test the cases where we catch expected exceptions and raise a custom 422 APIException.
        """
        self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        creation_request_payload = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_2,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
        }

        with mock.patch(
            'enterprise_subsidy.apps.subsidy.models.Subsidy.redeem',
            side_effect=exception_to_raise,
            autospec=True,
        ) as mocked_redeem:
            response = self.client.post(url, creation_request_payload)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        mocked_redeem.assert_called_once_with(
            self.subsidy_1,  # redeem is a bound method, but we have to patch via the module.
            STATIC_LMS_USER_ID,
            self.content_key_2,
            uuid.UUID(self.subsidy_access_policy_1_uuid),
            idempotency_key='my-idempotency-key',
            requested_price_cents=None,
            metadata=None,
        )
        assert response.json() == {
            'detail': str(exception_to_raise),
            'code': expected_error_code,
        }

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.lms_user_client")
    def test_operator_creation_requested_price_invalid(
        self,
        mock_lms_user_client,
        mock_get_content_summary,
        mock_price_for_content,
        mock_enterprise_client
    ):
        """
        Tests that the admin transaction creation endpoint responds with a 422
        when creating a transaction for an invalid requested price.
        """
        self.set_up_operator()

        canonical_price_cents = 1000
        # request only half of the canonical price, which falls outside default allowable interval
        requested_price_cents = 500
        mock_lms_user_client.return_value.best_effort_user_data.return_value = {
            'email': self.lms_user_email,
        }
        mock_enterprise_client.enroll.return_value = 'my-fulfillment-id'
        mock_price_for_content.return_value = canonical_price_cents
        mock_get_content_summary.return_value = {
            'content_uuid': self.content_key_1,
            'content_key': self.content_key_1,
            'content_title': self.content_title_1,
            'source': 'edX',
            'mode': 'verified',
            'content_price': canonical_price_cents,
            'geag_variant_id': None,
        }
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        # use the same inputs as existing_transaction
        request_data = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_1,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
            'requested_price_cents': requested_price_cents,
            'metadata': {
                'foo': 'bar',
            },
        }

        response = self.client.post(url, request_data)

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        expected_error_detail = [
            f'Requested price {requested_price_cents} for {self.content_key_1} outside of '
            f'acceptable interval on canonical course price of {canonical_price_cents}.'
        ]
        assert response.json() == {
            'detail': str(expected_error_detail),
            'code': ErrorCodes.INVALID_REQUESTED_PRICE,
        }

    def test_operator_creation_required_fields_validation_eror(self):
        """
        Tests that an authenticated operator receives a 400 response
        when attempting to create without all of the required fields being present.
        """
        self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        payload = {
            'anything': 'goes',
            'requested_price_cents': -100,
        }

        response = self.client.post(url, payload)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {
            'content_key': ['This field is required.'],
            'lms_user_id': ['This field is required.'],
            'subsidy_access_policy_uuid': ['This field is required.'],
            'requested_price_cents': ['Ensure this value is greater than or equal to 0.'],
        }

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    def test_operator_creation_happy_path_transaction_exists(self, mock_price_for_content, mock_enterprise_client):
        """
        Tests that the admin transaction creation endpoint responds with a 200
        when creating a transaction that already exists.
        """
        self.set_up_operator()

        existing_transaction = TransactionFactory(
            uuid=self.subsidy_1_transaction_1_uuid,
            state=TransactionStateChoices.COMMITTED,
            quantity=-1000,
            ledger=self.subsidy_1.ledger,
            lms_user_id=STATIC_LMS_USER_ID,
            subsidy_access_policy_uuid=self.subsidy_access_policy_1_uuid,
            content_key=self.content_key_1,
            fulfillment_identifier=uuid.uuid4(),
            idempotency_key='my-idempotency-key',
        )

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        # use the same inputs as existing_transaction
        request_data = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_1,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
        }

        response = self.client.post(url, request_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(mock_price_for_content.called)
        self.assertFalse(mock_enterprise_client.called)

        response_data = response.json()
        assert response_data["idempotency_key"] == request_data['idempotency_key']
        assert response_data["content_key"] == request_data["content_key"]
        assert response_data["lms_user_id"] == request_data["lms_user_id"]
        assert response_data["subsidy_access_policy_uuid"] == request_data["subsidy_access_policy_uuid"]
        assert response_data["metadata"] is None
        assert response_data["unit"] == existing_transaction.ledger.unit
        assert response_data["quantity"] == -1000
        assert response_data["fulfillment_identifier"] == str(existing_transaction.fulfillment_identifier)
        assert response_data["reversal"] is None
        assert response_data["state"] == TransactionStateChoices.COMMITTED

    @mock.patch('enterprise_subsidy.apps.subsidy.models.is_geag_fulfillment', return_value=False)
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.lms_user_client")
    @ddt.data(True, False)
    def test_operator_creation_happy_path_201(
        self,
        use_requested_price,
        mock_lms_user_client,
        mock_get_content_summary,
        mock_price_for_content,
        mock_enterprise_client,
        mock_is_geag_fulfillment,
    ):
        """
        Tests that the admin transaction creation endpoint responds with a 201
        when creating a transaction, and no matching transaction already exists.
        """
        self.set_up_operator()

        canonical_price_cents = 1000
        requested_price_cents = 900  # only in use if use_requested_price is True
        mock_lms_user_client.return_value.best_effort_user_data.return_value = {
            'email': self.lms_user_email,
        }
        mock_enterprise_client.enroll.return_value = 'my-fulfillment-id'
        mock_price_for_content.return_value = canonical_price_cents
        mock_get_content_summary.return_value = {
            'content_uuid': self.content_key_1,
            'content_key': self.content_key_1,
            'content_title': self.content_title_1,
            'source': 'edX',
            'mode': 'verified',
            'content_price': canonical_price_cents,
            'geag_variant_id': None,
        }
        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])
        # use the same inputs as existing_transaction
        request_data = {
            'lms_user_id': STATIC_LMS_USER_ID,
            'content_key': self.content_key_1,
            'subsidy_access_policy_uuid': self.subsidy_access_policy_1_uuid,
            'idempotency_key': 'my-idempotency-key',
            'metadata': {
                'foo': 'bar',
            },
        }
        if use_requested_price:
            request_data['requested_price_cents'] = requested_price_cents

        response = self.client.post(url, request_data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Read the transaction and also assert we passed it through to the enroll() call
        created_transaction = Transaction.objects.get(idempotency_key='my-idempotency-key')
        mock_price_for_content.assert_called_with(self.content_key_1)
        mock_enterprise_client.enroll.assert_called_once_with(
            STATIC_LMS_USER_ID,
            self.content_key_1,
            created_transaction,
        )

        response_data = response.json()
        assert response_data["idempotency_key"] == request_data['idempotency_key']
        assert response_data["content_key"] == request_data["content_key"]
        assert response_data["lms_user_id"] == request_data["lms_user_id"]
        assert response_data["subsidy_access_policy_uuid"] == request_data["subsidy_access_policy_uuid"]
        assert response_data["metadata"] == {'foo': 'bar'}
        assert response_data["unit"] == self.subsidy_1.ledger.unit
        assert response_data["fulfillment_identifier"] == 'my-fulfillment-id'
        assert response_data["reversal"] is None
        assert response_data["state"] == TransactionStateChoices.COMMITTED
        expected_quantity = -1 * (requested_price_cents if use_requested_price else canonical_price_cents)
        assert response_data["quantity"] == expected_quantity
