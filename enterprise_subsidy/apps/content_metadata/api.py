"""
Python API for gathering content metadata for content identifiers
during subsidy redemption and fulfillment.
"""
import logging
from decimal import Decimal

from django.conf import settings
from edx_django_utils.cache import TieredCache

from enterprise_subsidy.apps.api_client.enterprise_catalog import (
    EnterpriseCatalogApiClient,
    EnterpriseCatalogApiClientV2
)
from enterprise_subsidy.apps.core.utils import versioned_cache_key
from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from .constants import DEFAULT_CONTENT_PRICE, CourseModes, ProductSources

logger = logging.getLogger(__name__)


CONTENT_MODES_BY_PRODUCT_SOURCE = {
    ProductSources.EDX.value: CourseModes.EDX_VERIFIED.value,
    # TODO: additionally support other course modes/types beyond Executive Education for the 2U product source
    ProductSources.TWOU.value: CourseModes.EXECUTIVE_EDUCATION.value,
}

CACHE_NAMESPACE = 'content_metadata'
CONTENT_METADATA_CACHE_TIMEOUT = getattr(settings, 'CONTENT_METADATA_CACHE_TIMEOUT', 60 * 30)


def content_metadata_for_customer_cache_key(enterprise_customer_uuid, content_key):
    """
    Returns a versioned cache key that includes the customer uuid and content_key.
    """
    return versioned_cache_key(CACHE_NAMESPACE, enterprise_customer_uuid, content_key)


def content_metadata_cache_key(content_key):
    """
    Returns a versioned cache key that includes the customer uuid and content_key.
    """
    return versioned_cache_key(CACHE_NAMESPACE, content_key)


class ContentMetadataApi:
    """
    An API for interacting with enterprise catalog content metadata.
    """

    def price_for_content_fallback(self, content_data, course_run_data):
        """
        Fallback logic for `price_for_content` logic if the `normalized_metadata_by_run` field is None.
        The fallback logic is the original logic for determining the `content_price` before
        using normalized metadata as the first source of truth for `content_price`.
        """
        content_price = None

        product_source = self.product_source_for_content(content_data)
        if product_source == ProductSources.TWOU.value:
            enrollment_mode_for_content = self.mode_for_content(content_data)
            for entitlement in content_data.get('entitlements', []):
                if entitlement.get('mode') == enrollment_mode_for_content:
                    content_price = entitlement.get('price')
        else:
            content_price = course_run_data.get('first_enrollable_paid_seat_price')

        if not content_price:
            logger.info(
                f"Could not determine price for content key {content_data.get('key')} "
                f"and course run key {course_run_data.get('key')}, setting to default."
            )
            content_price = DEFAULT_CONTENT_PRICE

        return content_price

    def price_for_content(self, content_data, course_run_data):
        """
        Helper to return the "official" price for content.
        The endpoint at ``self.content_metadata_url`` will always return price fields
        as USD (dollars), possibly as a string or a float.  This method converts
        those values to USD cents as an integer.
        """
        content_price = None
        course_run_key = course_run_data.get('key')

        if course_run_key in content_data.get('normalized_metadata_by_run', {}):
            if normalized_price := content_data['normalized_metadata_by_run'][course_run_key].get('content_price'):
                content_price = normalized_price

        if not content_price:
            content_price = self.price_for_content_fallback(content_data, course_run_data)

        return int(Decimal(content_price) * CENTS_PER_DOLLAR)

    def mode_for_content(self, content_data):
        """
        Helper to extract the relevant enrollment mode for a piece of content metadata.
        """
        product_source = self.product_source_for_content(content_data)
        return CONTENT_MODES_BY_PRODUCT_SOURCE.get(product_source, CourseModes.EDX_VERIFIED.value)

    def product_source_for_content(self, content_data):
        """
        Helps get the product source string, given a dict of ``content_data``.
        """
        if product_source := content_data.get('product_source'):
            source_name = product_source.get('slug')
            if source_name in CONTENT_MODES_BY_PRODUCT_SOURCE:
                return source_name
        return ProductSources.EDX.value

    def get_geag_variant_id_for_content(self, content_identifier, content_data):
        """
        Get a GEAG ``variant_id`` for the given content.

        Args:
            content_identifier (str): The content for which to get a variant.
            content_data (dict): The content metadata dict fetched from the enterprise-catalog API.

        Returns:
            bool: The ``variant_id`` if one is found, or None otherwise.

        Notes:
            * In the GEAG system a ``variant_id`` is aka a ``product_id``.
            * If ``content_identifier`` is a course key, the variant returned will correspond to the advertised run.
            * If ``content_identifier`` is a course run key, the variant returned will correspond to that specific run,
              instead of the advertised run.
            * If, for some reason, a ``variant_id`` is not found inside the course run metadata, fallback to reading it
              from the deprecated ``additional_metadata`` dict.
        """
        course_run_content = self.get_course_run(content_identifier, content_data)
        variant_id = course_run_content.get('variant_id')
        # If no variant_id is found, and this is indeed an Exec Ed course, check the deprecated `additional_metadata`.
        if not variant_id:
            if additional_metadata := content_data.get('additional_metadata'):
                variant_id = additional_metadata.get('variant_id')
        return variant_id

    def enroll_by_date_for_content(self, course_run_data, content_mode):
        """
        Determines the enrollment deadline for the given ``course_run_data``.

        Args:
            course_run_data: A dictionary of metadata pertaining to a course run.
            content_mode: The (already computed) course mode for the course run.

        Returns:
            A datetime string, or possibly null.
        """
        # For edx-verified mode course runs, first try to extract
        # the verified upgrade deadline from the course run's seat
        # associated with the given content_mode
        upgrade_deadline = None
        if content_mode == CourseModes.EDX_VERIFIED.value:
            seats_for_mode = [
                seat for seat in course_run_data.get('seats', [])
                if seat.get('type') == content_mode
            ]
            if seats_for_mode:
                seat = seats_for_mode[0]
                upgrade_deadline = seat.get('upgrade_deadline_override') or seat.get('upgrade_deadline')

        # Return the upgrade deadline. If no such deadline exists,
        # or if we're dealing with another course mode (e.g. exec ed),
        # use the `enrollment_end` of the course run.
        return upgrade_deadline or course_run_data.get('enrollment_end')

    def summary_data_for_content(self, content_identifier, content_data):
        """
        Returns a summary dict specifying the content_uuid, content_key, source, and content_price
        for a dict of content metadata.
        """
        course_run_content = self.get_course_run(content_identifier, content_data)
        content_mode = self.mode_for_content(content_data)
        return {
            'content_title': content_data.get('title'),
            'content_uuid': content_data.get('uuid'),
            'content_key': content_data.get('key'),
            'course_run_uuid': course_run_content.get('uuid'),
            'course_run_key': course_run_content.get('key'),
            'course_run_start_date': course_run_content.get('start'),
            'source': self.product_source_for_content(content_data),
            'mode': content_mode,
            'content_price': self.price_for_content(content_data, course_run_content),
            'enroll_by_date': self.enroll_by_date_for_content(course_run_content, content_mode),
            'geag_variant_id': self.get_geag_variant_id_for_content(content_identifier, content_data),
        }

    def get_course_run(self, content_identifier, content_data):
        """
        Given a content_identifier (key, run key, uuid) extract the appropriate course_run.
        When given a run key or uuid for a run, extract that. When given a course key or
        course uuid, extract the advertised course_run.
        """
        if content_data.get('content_type') == 'courserun':
            return content_data

        course_run_identifier = content_identifier
        # if the supplied content_identifer refers to the course, look for an advertised run
        if content_identifier == content_data.get('key') or content_identifier == content_data.get('uuid'):
            course_run_identifier = content_data.get('advertised_course_run_uuid')
        for course_run in content_data.get('course_runs', []):
            if course_run_identifier == course_run.get('key') or course_run_identifier == course_run.get('uuid'):
                return course_run
        return {}

    def get_content_summary(self, enterprise_customer_uuid, content_identifier, **kwargs):
        """
        Returns a summary dict some content metadata, makes the client call
        """
        course_details = self.get_content_metadata_for_customer(
            enterprise_customer_uuid,
            content_identifier,
            **kwargs,
        )
        return self.summary_data_for_content(content_identifier, course_details)

    def get_course_price(self, enterprise_customer_uuid, content_identifier):
        """
        Returns the price of a content as it's defined within the entitlements of the Enterprise Catalog's content
        metadata record for a piece of content.

        Arguments:
            enterprise_customer_uuid (UUID): UUID of the customer associated with an enterprise
            content_identifier (str): **Either** the content UUID or content key identifier for a content record.
                Note: the content needs to be owned by a catalog associated with the provided customer else this
                method will throw an HTTPError.
        Returns:
            Pricing (list of dicts): Array containing mappings of an individual content's course price associated with
            a each of it's course mode
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception. A 404 exception will be thrown if the content
            does not exist, or is not present in a catalog associated with the customer.
        """
        course_details = self.get_content_metadata_for_customer(
            enterprise_customer_uuid,
            content_identifier
        )
        course_run_data = self.get_course_run(content_identifier, course_details)
        return self.price_for_content(course_details, course_run_data)

    def get_product_source(self, enterprise_customer_uuid, content_identifier):
        """
        Returns the a specific piece of content's product source as it's defined within the content metadata of the
        Enterprise Catalog service.

        Arguments:
            enterprise_customer_uuid (UUID): UUID of the customer associated with an enterprise
            content_identifier (str): **Either** the content UUID or content key identifier for a content record.
                Note: the content needs to be owned by a catalog associated with the provided customer else this
                method will throw an HTTPError.
        Returns:
            Either `2U` or `edX` based on the content's product source content metadata field
        Raises:
            requests.exceptions.HTTPError: if service is down/unavailable or status code comes back >= 300,
            the method will log and throw an HTTPError exception. A 404 exception will be thrown if the content
            does not exist, or is not present in a catalog associated with the customer.
        """
        course_details = self.get_content_metadata_for_customer(
            enterprise_customer_uuid,
            content_identifier
        )
        return self.product_source_for_content(course_details)

    def get_geag_variant_id(self, enterprise_customer_uuid, content_identifier):
        """
        Returns the GetSmarter product variant id or None
        """
        return self.get_content_summary(enterprise_customer_uuid, content_identifier).get('geag_variant_id')

    @staticmethod
    def get_content_metadata(content_identifier, **kwargs):
        """
        Fetches only base details on a content metadata record from a tiered (request + django) cache;
        or fetches it from the enterprise-catalog API if not present in teh cache, and then caches the result.
        """
        cache_key = content_metadata_cache_key(content_identifier)
        cached_response = TieredCache.get_cached_response(cache_key)
        if cached_response.is_found:
            return cached_response.value

        course_details = EnterpriseCatalogApiClient().get_content_metadata(
            content_identifier,
            **kwargs,
        )
        if course_details:
            TieredCache.set_all_tiers(
                cache_key,
                course_details,
                django_cache_timeout=CONTENT_METADATA_CACHE_TIMEOUT,
            )
        else:
            logger.warning('Could not fetch metadata for content %s', content_identifier)
        return course_details

    @staticmethod
    def get_content_metadata_for_customer(enterprise_customer_uuid, content_identifier, **kwargs):
        """
        Fetches both base and customer specific details about the given content from a tiered (request + django) cache;
        or it fetches from the enterprise-catalog API if not present in the cache, and then caches that result.
        """
        cache_key = content_metadata_for_customer_cache_key(enterprise_customer_uuid, content_identifier)
        cached_response = TieredCache.get_cached_response(cache_key)
        if cached_response.is_found:
            return cached_response.value

        course_details = EnterpriseCatalogApiClientV2().get_content_metadata_for_customer(
            enterprise_customer_uuid,
            content_identifier,
            **kwargs,
        )
        if course_details:
            TieredCache.set_all_tiers(
                cache_key,
                course_details,
                django_cache_timeout=CONTENT_METADATA_CACHE_TIMEOUT,
            )
        else:
            logger.warning(
                'Could not fetch metadata for customer %s, content %s',
                enterprise_customer_uuid,
                content_identifier,
            )
        return course_details
