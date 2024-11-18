"""
Enterprise Catalog api client for the subsidy service.
"""
import logging
from urllib.parse import urljoin

import requests
from django.conf import settings

from enterprise_subsidy.apps.api_client.base_oauth import BaseOAuthClient

logger = logging.getLogger(__name__)


class EnterpriseCatalogApiClient(BaseOAuthClient):
    """
    API client for calls to the enterprise service.
    """
    api_version = 'v1'

    def __init__(self):
        self.api_base_url = urljoin(settings.ENTERPRISE_CATALOG_URL, f'api/{self.api_version}/')
        self.metadata_endpoint = urljoin(self.api_base_url, 'content-metadata/')
        self.enterprise_customer_endpoint = urljoin(self.api_base_url, 'enterprise-customer/')
        super().__init__()

    def enterprise_customer_url(self, enterprise_customer_uuid):
        return urljoin(
            self.enterprise_customer_endpoint,
            f"{enterprise_customer_uuid}/",
        )

    def content_metadata_url(self, enterprise_customer_uuid, content_identifier):
        return urljoin(
            self.enterprise_customer_url(enterprise_customer_uuid),
            f'content-metadata/{content_identifier}/'
        )

    def get_content_metadata(self, content_identifier, **kwargs):
        """
        Returns base, non-customer specific data on an individual piece of content.

        Arguments:
                content_identifier (str): **Either** the content UUID or content key identifier for a content record.
        """
        content_metadata_url = self.metadata_endpoint
        query_params = {"content_identifiers": [content_identifier]}
        try:
            response = self.client.get(content_metadata_url, params=query_params)
            response.raise_for_status()
            response_json = response.json()
            return response_json['results'][0] if response_json['results'] else None
        except requests.exceptions.HTTPError as exc:
            if hasattr(response, 'text'):
                logger.exception(
                    f"Failed to fetch content metadata: {content_identifier} from the catalog service."
                    f"Failed with error: {response.text}"
                )
            raise exc

    def get_content_metadata_for_customer(
        self, enterprise_customer_uuid, content_identifier, skip_customer_fetch=False, **kwargs
    ):
        """
        Returns Enterprise Customer related data for a specified piece on content.

        Arguments:
            enterprise_customer_uuid (UUID): UUID of the customer associated with an enterprise
            content_identifier (str): **Either** the content UUID or content key identifier for a content record.
                Note: the content needs to be owned by a catalog associated with the provided customer else this
                method will throw an HTTPError.
            skip_customer_fetch (bool): Forces enterprise-catalog to skip a sub-call to an edx-enterprise
                API endpoint running in the edx-platform runtime. This sub-call helps the catalog service
                understand the last time a catalog's customer record was modified, and also helps
                to construct course and course run enrollment URLs that are usually not needed
                in the context of enterprise-subsidy or callers of the EnterpriseCustomerViewSet.
                Defaults to False.
        Returns:
            response (dict): JSON response object associated with a content metadata record
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception. A 404 exception will be thrown if the content
            does not exist, or is not present in a catalog associated with the customer.
        """
        content_metadata_url = self.content_metadata_url(enterprise_customer_uuid, content_identifier)
        query_params = {}
        if skip_customer_fetch:
            query_params['skip_customer_fetch'] = skip_customer_fetch
        try:
            response = self.client.get(content_metadata_url, params=query_params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            if hasattr(response, 'text'):
                logger.error(
                    f'Failed to fetch enterprise customer data for {enterprise_customer_uuid} because {response.text}',
                )
            raise exc


class EnterpriseCatalogApiClientV2(EnterpriseCatalogApiClient):
    """
    V2 API client for calls to the enterprise service.

    Right now this just extends the V1 class to avoid duplicate logic.
    """
    api_version = 'v2'

    def get_content_metadata(self, content_identifier, **kwargs):
        """
        Non-customer-based endpoint does not currently exist with a v2 version.
        """
        raise NotImplementedError
