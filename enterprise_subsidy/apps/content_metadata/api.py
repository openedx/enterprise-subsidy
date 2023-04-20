"""
Python API for gathering content metadata for content identifiers
during subsidy redemption and fulfillment.
"""
import logging
from decimal import Decimal

from enterprise_subsidy.apps.subsidy.constants import CENTS_PER_DOLLAR

from .constants import EDX_PRODUCT_SOURCE, EDX_VERIFIED_COURSE_MODE, EXECUTIVE_EDUCATION_MODE, TWOU_PRODUCT_SOURCE

logger = logging.getLogger(__name__)


CONTENT_MODES_BY_PRODUCT_SOURCE = {
    EDX_PRODUCT_SOURCE: EDX_VERIFIED_COURSE_MODE,
    TWOU_PRODUCT_SOURCE: EXECUTIVE_EDUCATION_MODE,
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
    return CONTENT_MODES_BY_PRODUCT_SOURCE.get(product_source, EDX_VERIFIED_COURSE_MODE)


def product_source_for_content(content_data):
    """
    Helps get the product source string, given a dict of ``content_data``.
    """
    if product_source := content_data.get('product_source'):
        source_name = product_source.get('name')
        if source_name in CONTENT_MODES_BY_PRODUCT_SOURCE:
            return source_name
    return EDX_PRODUCT_SOURCE


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


def get_content_metadata(content_key=None, content_uuid=None):
    """
    Returns a dictionary of content metadata for the given
    identifier.
    At least one of ``content_key`` or ``content_uuid`` is required.
    If both are non-null, ``content_key`` will be used as the primary
    lookup identifier.
    """
    identifier = content_key or content_uuid
    if not identifier:
        # pylint: disable=broad-exception-raised
        raise Exception('One of content_key or content_uuid is required')
    raise NotImplementedError
