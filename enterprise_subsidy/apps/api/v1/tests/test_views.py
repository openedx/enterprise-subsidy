"""
Tests for views.
"""
import json
import uuid

import ddt
from rest_framework import status
from rest_framework.reverse import reverse

from enterprise_subsidy.apps.api.v1.tests.mixins import APITestMixin
from enterprise_subsidy.apps.subsidy.tests.factories import SubsidyFactory


class APITestBase(APITestMixin):
    """
    Provides shared test resource setup between curation-related API test classes.

    Contains boilerplate to create a couple of subsidies with related ledgers and starting transactions.
    """
    def setUp(self):
        super().setUp()

        # Create the main test objects that the test users should be able to access.
        self.subsidy_one = SubsidyFactory(enterprise_customer_uuid=self.enterprise_uuid, starting_balance=10000)
        self.ledger_one = self.subsidy_one.ledger
        self.transaction_one = self.subsidy_one.initialize_ledger()

        # Create an extra subsidy corresponding to a different enterprise customer an unprivileged default test user
        # should not be able to access.
        self.subsidy_two = SubsidyFactory(enterprise_customer_uuid=uuid.uuid4(), starting_balance=10000)
        self.ledger_two = self.subsidy_two.ledger
        self.transaction_two = self.subsidy_two.initialize_ledger()


@ddt.ddt
class TransactionViewSetTests(APITestBase):
    """
    Test TransactionViewSet.
    """

    # Uncomment this later once we have segment events firing.
    # @mock.patch('enterprise_subsidy.apps.api.v1.event_utils.track_event')
    # def test_create(self, mock_track_event):
    def test_create(self):
        """
        Test create Transaction, happy case.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()
        post_data = {
            "subsidy_uuid": str(self.subsidy_one.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_201_CREATED
        create_response_data = response.json()
        assert len(create_response_data["uuid"]) == 36
        assert create_response_data["idempotency_key"]  # TODO: fix this once the idempotency key format is finalized.
        assert create_response_data["content_key"] == post_data["content_key"]
        assert create_response_data["lms_user_id"] == post_data["learner_id"]
        assert create_response_data["subsidy_access_policy_uuid"] == post_data["access_policy_uuid"]
        assert json.loads(create_response_data["metadata"]) == {}
        assert create_response_data["unit"] == self.ledger_one.unit
        assert create_response_data["quantity"] < 0  # No need to be exact at this time, I'm just testing create works.
        assert create_response_data["reference_id"]  # Ditto ^
        assert create_response_data["reference_type"]  # Ditto ^
        assert create_response_data["reversal"] is None
        assert create_response_data["state"] == "committed"

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
        #         "enterprise_customer_uuid": str(self.subsidy_one.enterprise_customer_uuid),
        #         "subsidy_uuid": str(self.curation_config_one.uuid),
        #     },
        # )

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
            "subsidy_uuid": str(self.subsidy_one.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        # Just make sure there's any parseable json which is likely to contain an explanation of the error.
        assert response.json()

    def test_create_invalid_subsidy_uuid(self):
        """
        Test create Transaction, failed due to invalid uuid.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_one.uuid) + "a",  # Make uuid invalid.
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "access_policy_uuid": str(uuid.uuid4()),
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "detail" in response.json()

    def test_create_invalid_access_policy_uuid(self):
        """
        Test create Transaction, failed due to invalid uuid.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_one.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "access_policy_uuid": str(uuid.uuid4()) + "a",  # Make uuid invalid.
        }
        response = self.client.post(url, post_data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Error" in response.json()

    @ddt.data("subsidy_uuid", "learner_id", "content_key", "access_policy_uuid")
    def test_create_missing_inputs(self, missing_post_arg):
        """
        Test create Transaction, 4xx due to missing inputs.
        """
        url = reverse("api:v1:transaction-list")
        # Create privileged staff user that should be able to create Transactions.
        self.set_up_operator()

        post_data = {
            "subsidy_uuid": str(self.subsidy_one.uuid),
            "learner_id": 1234,
            "content_key": "course-v1:edX-test-course",
            "access_policy_uuid": str(uuid.uuid4()),
        }
        del post_data[missing_post_arg]
        response = self.client.post(url, post_data)
        assert response.status_code >= 400 and response.status_code < 500
        # Just make sure there's any parseable json which is likely to contain an explanation of the error.
        assert response.json()
