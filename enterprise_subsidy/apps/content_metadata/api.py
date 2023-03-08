"""
Python API for gathering content metadata for content identifiers
during subsidy redemption and fulfillment.
"""


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
