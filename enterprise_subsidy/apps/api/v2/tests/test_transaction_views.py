"""
Tests for the v2 transaction views.
"""
import urllib
import uuid
from unittest import mock

import ddt
from edx_rbac.utils import ALL_ACCESS_CONTEXT
from openedx_ledger.models import LedgerLockAttemptFailed, Transaction, TransactionStateChoices, UnitChoices
from openedx_ledger.test_utils.factories import TransactionFactory
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_subsidy.apps.api.v1.tests.mixins import STATIC_ENTERPRISE_UUID, STATIC_LMS_USER_ID, APITestMixin
from enterprise_subsidy.apps.subsidy.constants import SYSTEM_ENTERPRISE_ADMIN_ROLE, SYSTEM_ENTERPRISE_LEARNER_ROLE
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory

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
    # Add an extra UUID for any failed transaction that
    # a subclass may need to use
    failed_transaction_uuid = str(uuid.uuid4())

    subsidy_access_policy_1_uuid = str(uuid.uuid4())
    subsidy_access_policy_2_uuid = str(uuid.uuid4())

    content_key_1 = "course-v1:edX+test+course.1"
    content_key_2 = "course-v1:edX+test+course.2"

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
            subsidy_access_policy_uuid=cls.subsidy_access_policy_2_uuid,
            content_key=cls.content_key_2,
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
            subsidy_access_policy_uuid=cls.subsidy_access_policy_1_uuid,
            content_key=cls.content_key_1,
        )

    @ddt.data(
        # Test that an admin can list all transactions in a subsidy within their enterprise.
        {
            "role": "admin",
            "subsidy_uuid": APITestBase.subsidy_1_uuid,
            "expected_response_status": status.HTTP_200_OK,
            "expected_response_uuids": [
                APITestBase.subsidy_1_transaction_1_uuid,
                APITestBase.subsidy_1_transaction_2_uuid,
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
            metadata=None,
        )
        assert response.json() == {'detail': 'Attempt to lock the Ledger failed, please try again.'}

    def test_operator_creation_required_fields_validation_eror(self):
        """
        Tests that an authenticated operator receives a 400 response
        when attempting to create without all of the required fields being present.
        """
        self.set_up_operator()

        url = reverse("api:v2:transaction-admin-list-create", args=[self.subsidy_1.uuid])

        response = self.client.post(url, {'anything': 'goes'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {
            'content_key': ['This field is required.'],
            'lms_user_id': ['This field is required.'],
            'subsidy_access_policy_uuid': ['This field is required.'],
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

    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client")
    @mock.patch("enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content")
    @mock.patch("enterprise_subsidy.apps.content_metadata.api.ContentMetadataApi.get_content_summary")
    def test_operator_creation_happy_path_201(
        self,
        mock_get_content_summary,
        mock_price_for_content,
        mock_enterprise_client
    ):
        """
        Tests that the admin transaction creation endpoint responds with a 201
        when creating a transaction, and no matching transaction already exists.
        """
        self.set_up_operator()

        mock_enterprise_client.enroll.return_value = 'my-fulfillment-id'
        mock_price_for_content.return_value = 1000
        mock_get_content_summary.return_value = {
            'content_uuid': self.content_key_1,
            'content_key': self.content_key_1,
            'source': 'edX',
            'mode': 'verified',
            'content_price': 10000,
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
        assert response_data["quantity"] == -1000
        assert response_data["fulfillment_identifier"] == 'my-fulfillment-id'
        assert response_data["reversal"] is None
        assert response_data["state"] == TransactionStateChoices.COMMITTED
