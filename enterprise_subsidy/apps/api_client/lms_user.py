"""
LMS User Data api client for the subsidy service.
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from enterprise_subsidy.apps.api_client.base_oauth import BaseOAuthClient

logger = logging.getLogger(__name__)


class LmsUserApiClient(BaseOAuthClient):
    """
    API client for LMS User Data.
    """
    api_base_url = settings.LMS_URL + '/api/user/v1'
    accounts_url = api_base_url + '/accounts'

    def user_account_url(self, lms_user_id):
        return f"{self.accounts_url}?lms_user_id={lms_user_id}"

    def get_user_data(self, lms_user_id):
        """
        Gets the data for an LMS User given their lms user id.

        Arguments:
            lms_user_id (int): LMS User Id of a learner
        Returns:
            response (dict): JSON response data
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception.
        """
        lms_account_url = self.user_account_url(lms_user_id)
        try:
            response = self.client.get(lms_account_url)
            response.raise_for_status()
            data = response.json()
            if data:
                return data.pop()
            else:
                return None
        except requests.exceptions.HTTPError as exc:
            if hasattr(response, 'text'):
                logger.error(
                    f'Failed to fetch user data for {lms_user_id} because {response.text}',
                )
            raise exc

    def best_effort_user_data(self, lms_user_id):
        """
        Gets the data for an LMS User given their lms user id.
        Tries to use cache.
        Rescues exceptions + logs without reraising.

        Arguments:
            lms_user_id (int): LMS User Id of a learner
        Returns:
            response (dict): JSON response data
        """
        try:
            cache_key = 'LmsUserApiClient:lms_user_id:{lms_user_id}'.format(lms_user_id=lms_user_id)
            user_data = cache.get(cache_key)

            if not isinstance(user_data, dict):
                user_data = self.get_user_data(lms_user_id)

                if not isinstance(user_data, dict):
                    logger.warning('Received unexpected user_data for lms_user_id %s', lms_user_id)
                    return None

                cache.set(cache_key, user_data, settings.LMS_USER_DATA_CACHE_TIMEOUT)
            return user_data
        except requests.exceptions.HTTPError:
            logger.exception(
                f'Failed best effort attempt to fetch user data for {lms_user_id}',
            )
            return None
