"""
Python API for gathering content metadata for content identifiers
during subsidy redemption and fulfillment.
"""
import logging
from decimal import Decimal

from enterprise_subsidy.apps.api_client.enterprise_catalog import EnterpriseCatalogApiClient
from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from .constants import CourseModes, ProductSources

logger = logging.getLogger(__name__)


CONTENT_MODES_BY_PRODUCT_SOURCE = {
    ProductSources.EDX.value: CourseModes.EDX_VERIFIED.value,
    ProductSources.TWOU.value: CourseModes.EXECUTIVE_EDUCATION.value,
}


def price_for_content(content_data):
    """
    Helper to return the "official" price for content.
    The endpoint at ``self.content_metadata_url`` will always return price fields
    as USD (dollars), possibly as a string or a float.  This method converts
    those values to USD cents as an integer.
    """
    content_price = None
    if content_data.get('first_enrollable_paid_seat_price'):
        content_price = content_data['first_enrollable_paid_seat_price']

    if not content_price:
        enrollment_mode_for_content = mode_for_content(content_data)
        for entitlement in content_data.get('entitlements', []):
            if entitlement.get('mode') == enrollment_mode_for_content:
                content_price = entitlement.get('price')

    if content_price:
        return int(Decimal(content_price) * CENTS_PER_DOLLAR)
    return None


def mode_for_content(content_data):
    """
    Helper to extract the relevant enrollment mode for a piece of content metadata.
    """
    product_source = product_source_for_content(content_data)
    return CONTENT_MODES_BY_PRODUCT_SOURCE.get(product_source, CourseModes.EDX_VERIFIED.value)


def product_source_for_content(content_data):
    """
    Helps get the product source string, given a dict of ``content_data``.
    """
    if product_source := content_data.get('product_source'):
        source_name = product_source.get('name')
        if source_name in CONTENT_MODES_BY_PRODUCT_SOURCE:
            return source_name
    return ProductSources.EDX.value


def get_geag_variant_id_for_content(content_data):
    """
    Returns the GEAG ``variant_id`` or ``None``, given a dict of ``content_data``.
    """
    variant_id = None
    if additional_metadata := content_data.get('additional_metadata'):
        variant_id = additional_metadata.get('variant_id')
    return variant_id


def summary_data_for_content(content_data):
    """
    Returns a summary dict specifying the content_uuid, content_key, source, and content_price
    for a dict of content metadata.
    """
    return {
        'content_uuid': content_data.get('uuid'),
        'content_key': content_data.get('key'),
        'source': product_source_for_content(content_data),
        'mode': mode_for_content(content_data),
        'content_price': price_for_content(content_data),
        'geag_variant_id': get_geag_variant_id_for_content(content_data),
    }

def get_content_summary(enterprise_customer_uuid, content_identifier):
    """
    Returns a summary dict some content metadata, makes the client call
    """
    course_details = get_content_metadata(enterprise_customer_uuid, content_identifier)
    return summary_data_for_content(course_details)

def get_content_metadata(enterprise_customer_uuid, content_identifier):
    """
    Returns a dictionary of content metadata for the given
    identifier.
    """
    catalog_client = EnterpriseCatalogApiClient()
    return catalog_client.get_content_metadata_for_customer(enterprise_customer_uuid, content_identifier)


def get_course_price(enterprise_customer_uuid, content_identifier):
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
    course_details = get_content_metadata(enterprise_customer_uuid, content_identifier)
    return price_for_content(course_details)


def get_product_source(enterprise_customer_uuid, content_identifier):
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
    course_details = get_content_metadata(enterprise_customer_uuid, content_identifier)
    return product_source_for_content(course_details)
