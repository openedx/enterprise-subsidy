"""
Enterprise api client for the subsidy service.
"""
import logging
import os

import requests
from django.conf import settings

from enterprise_subsidy.apps.api_client.base_oauth import BaseOAuthClient

logger = logging.getLogger(__name__)


class EnterpriseApiClient(BaseOAuthClient):
    """
    API client for calls to the enterprise service.
    """
    api_base_url = settings.LMS_URL + '/enterprise/api/v1/'
    enterprise_customer_endpoint = api_base_url + 'enterprise-customer/'

    def enterprise_customer_url(self, enterprise_customer_uuid):
        return os.path.join(
            self.enterprise_customer_endpoint,
            f"{enterprise_customer_uuid}/",
        )

    def enterprise_customer_bulk_enrollment_url(self, enterprise_customer_uuid):
        return os.path.join(
            self.enterprise_customer_url(enterprise_customer_uuid),
            "enroll_learners_in_courses/",
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

    def enroll_enterprise_learner_in_courserun(
        self,
        transaction_id,
        user_email,
        course_run_key,
        enterprise_customer_uuid
    ):
        """
        Creates a single subsidy enrollment in a course run for an enterprise learner.

        Arguments:
            transaction_id (UUID): UUID representation of the subsidy transaction for the enrollment
            user_email (str): Email value of the user to be enrolled
            course_run_key (str): Course run key value of the course run to be enrolled in
            enterprise_customer_uuid (UUID): UUID representation of the customer that the enrollment will be linked to
        Returns:
            response (dict): JSON response data
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception.
        """
        enrollments_info = [{
            'email': user_email,
            'course_run_key': course_run_key,
            'transaction_id': transaction_id,
        }]
        return self.bulk_enroll_enterprise_learners(enterprise_customer_uuid, enrollments_info)

    def bulk_enroll_enterprise_learners(self, enterprise_customer_uuid, enrollments_info):
        """
        Calls the Enterprise Bulk Enrollment API to enroll learners in courses.

        Arguemnts:
            enterprise_customer_uuid (UUID): UUID representation of the customer that the enrollment will be linked to
            enrollment_info (list[dicts]): List of enrollment information required to enroll.
                Each index must contain key/value pairs:
                    email: the email of the learner to be enrolled
                    course_run_key: the course run key to be enrolled in by the user
                    transaction_id: uuid represenation of the transaction for the enrollment

                Example::
                    [
                        {
                            'email': 'newuser2@test.com',
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
        try:
            response = self.client.post(
                bulk_enrollment_url,
                json=options,
                timeout=settings.BULK_ENROLL_REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            logger.error(
                f'Failed to generate enterprise enrollments for enterprise: {enterprise_customer_uuid} '
                f'with options: {options}. Failed with error: {exc}'
            )
            raise exc
