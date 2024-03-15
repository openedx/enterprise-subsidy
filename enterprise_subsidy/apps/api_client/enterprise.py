"""
Enterprise api client for the subsidy service.
"""
import logging
import os
from datetime import timedelta

import requests
from django.conf import settings

from enterprise_subsidy.apps.api_client.base_oauth import BaseOAuthClient
from enterprise_subsidy.apps.core.utils import localized_utcnow

logger = logging.getLogger(__name__)

# Name of field in JSON response from bulk enrollment API that contains the value to be used as the reference to the
# newly created enrollment.
ENROLLMENT_REF_ID_FIELD_NAME = "enterprise_fulfillment_source_uuid"


class EnrollmentException(Exception):
    """
    Thrown if something goes wrong trying to create an enrollment.
    """


class EnterpriseApiClient(BaseOAuthClient):
    """
    API client for calls to the enterprise service.
    """
    api_base_url = settings.LMS_URL + '/enterprise/api/v1/'
    enterprise_customer_endpoint = api_base_url + 'enterprise-customer/'
    enterprise_subsidy_fulfillment_endpoint = api_base_url + 'enterprise-subsidy-fulfillment/'

    def enterprise_customer_url(self, enterprise_customer_uuid):
        return os.path.join(
            self.enterprise_customer_endpoint,
            f"{enterprise_customer_uuid}/",
        )

    def enterprise_fulfillment_url(self, enterprise_fulfillment_uuid):
        return os.path.join(
            self.enterprise_subsidy_fulfillment_endpoint,
            f"{enterprise_fulfillment_uuid}/"
        )

    def enterprise_customer_bulk_enrollment_url(self, enterprise_customer_uuid):
        return os.path.join(
            self.enterprise_customer_url(enterprise_customer_uuid),
            "enroll_learners_in_courses/",
        )

    def enterprise_fulfillment_cancel_url(self, enterprise_fulfillment_uuid):
        return os.path.join(
            self.enterprise_fulfillment_url(enterprise_fulfillment_uuid),
            "cancel-fulfillment",
        )

    def enterprise_fulfillment_unenrollments_url(self):
        return os.path.join(
            self.api_base_url,
            "operator/enterprise-subsidy-fulfillment/unenrolled/",
        )

    def get_enterprise_customer_data(self, enterprise_customer_uuid):
        """
        Gets the data for an EnterpriseCustomer with a given UUID.

        Arguments:
            enterprise_customer_uuid (UUID): UUID of the enterprise customer associated with an enterprise
        Returns:
            response (dict): JSON response data
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception.
        """
        enterprise_customer_url = self.enterprise_customer_url(enterprise_customer_uuid)
        try:
            response = self.client.get(enterprise_customer_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            if hasattr(response, 'text'):
                logger.error(
                    f'Failed to fetch enterprise customer data for {enterprise_customer_uuid} because {response.text}',
                )
            raise exc

    def enroll(self, lms_user_id, course_run_key, ledger_transaction):
        """
        Creates a single subsidy enrollment in a course run for an enterprise learner from a subsidy transaction.
        Arguments:
            lms_user_id (int): lms_user_id of the learner to be enrolled
            course_run_key (str): Course run key value of the course run to be enrolled in
            ledger_transaction (openedx_ledger.models.Transaction): the Transaction returned from the ledger
        Returns:
            reference_id (str): EnterpriseCourseEnrollment reference id for ledger transaction confirmation
        Raises:
            requests.exceptions.HTTPError:
                If service is down/unavailable or status code comes back >= 300, the method will log and throw an
                HTTPError exception.
            EnrollmentError:
                If enrollment response contained an unexpected output, such as missing data.
        """
        enrollment_info = {
            'user_id': lms_user_id,
            'course_run_key': course_run_key,
            'transaction_id': str(ledger_transaction.uuid),
        }
        # If late enrollment has been enabled for this transaction, inform the enterprise bulk enroll endpoint to bypass
        # any enrollment deadline validation.
        if ledger_transaction.metadata and ledger_transaction.metadata.get('allow_late_enrollment', False):
            enrollment_info['force_enrollment'] = True
        customer_uuid = ledger_transaction.ledger.subsidy.enterprise_customer_uuid
        response = self.bulk_enroll_enterprise_learners(customer_uuid, [enrollment_info])
        if "successes" not in response or len(response["successes"]) != 1:
            raise EnrollmentException("Enrollment response should contain exactly one successful enrollment.")
        enrollment_success_info = response["successes"][0]
        if ENROLLMENT_REF_ID_FIELD_NAME not in enrollment_success_info:
            raise EnrollmentException(
                f"Enrollment response missing a reference ID to the created object ({ENROLLMENT_REF_ID_FIELD_NAME})."
            )
        return enrollment_success_info.get(ENROLLMENT_REF_ID_FIELD_NAME)

    def bulk_enroll_enterprise_learners(self, enterprise_customer_uuid, enrollments_info):
        """
        Calls the Enterprise Bulk Enrollment API to enroll learners in courses.

        Arguments:
            enterprise_customer_uuid (UUID): UUID representation of the customer that the enrollment will be linked to
            enrollment_info (list[dicts]): List of enrollment information required to enroll.
                Each index must contain key/value pairs:
                    user_id: ID of the learner to be enrolled
                    course_run_key: the course run key to be enrolled in by the user
                    transaction_id: uuid representation of the transaction for the enrollment

                Example::
                    [
                        {
                            'user_id': 1234,
                            'course_run_key': 'course-v2:edX+FunX+Fun_Course',
                            'transaction_id': '84kdbdbade7b4fcb838f8asjke8e18ae',
                        },
                        ...
                    ]
        Returns:
            response (dict): JSON response data
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception.
        """
        bulk_enrollment_url = self.enterprise_customer_bulk_enrollment_url(enterprise_customer_uuid)
        options = {'enrollments_info': enrollments_info}
        response = self.client.post(
            bulk_enrollment_url,
            json=options,
            timeout=settings.BULK_ENROLL_REQUEST_TIMEOUT_SECONDS,
        )
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            logger.error(
                f'Failed to generate enterprise enrollments for enterprise: {enterprise_customer_uuid} '
                f'with options: {options}. Failed with error: {exc} and payload {response.json()}'
            )
            raise exc

    def cancel_fulfillment(self, enterprise_fulfillment_uuid):
        """
        Calls the Platform Enterprise Subsidy Enrollment API to cancel an enrollment.
        Arguments:
            enterprise_fulfillment_uuid (UUID): UUID representation of the subsidy enrollment to be cancelled
        Returns:
            response (dict): JSON response data
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception.
        """
        logger.info(
            f'Cancelling enterprise enrollment for enterprise_fulfillment_uuid: {enterprise_fulfillment_uuid}'
        )
        cancel_enrollment_url = self.enterprise_fulfillment_cancel_url(enterprise_fulfillment_uuid)
        try:
            response = self.client.post(cancel_enrollment_url)
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logger.error(
                f'Failed to cancel enterprise enrollment for enterprise_fulfillment_uuid: '
                f'{enterprise_fulfillment_uuid}. Failed with error: {exc}'
            )
            raise exc

    def fetch_recent_unenrollments(self):
        """
        Fetches enterprise enrollment objects that have been unenrolled within the last 24 hours.
        """
        unenrolled_subsidies_url = self.enterprise_fulfillment_unenrollments_url()
        unenrolled_cutoff = (localized_utcnow() - timedelta(hours=24 * 7)).isoformat()
        try:
            response = self.client.get(
                unenrolled_subsidies_url,
                params={"unenrolled_after": unenrolled_cutoff}
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as exc:
            logger.error(
                f'Failed to fetch recently unenrolled enterprise subsidies. Failed with error: {exc}'
            )
            raise exc
