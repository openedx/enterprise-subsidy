"""
Python API for interacting with fulfillment operations
related to subsidy redemptions.
"""
# pylint: disable=unused-import
from enterprise_subsidy.apps.content_metadata import api as content_metadata_api

from .constants import EXEC_ED_2U_COURSE_TYPES, OPEN_COURSES_COURSE_TYPES


def create_fulfillment(subsidy_uuid, lms_user_id, content_key, **metadata):
    """
    Creates a fulfillment.
    """
    raise NotImplementedError


def determine_fulfillment_client(subsidy_uuid, content_key):
    """
    Function stub.
    Determines which API client can fulfill a redemption for the given content_key.
    The implementation will likely want to follow a pattern like this:

    metadata = content_metadata_api.get_content_metadata(content_key)
    course_type = metadata.get('course_type')
    if course_type in EXEC_ED_2U_COURSE_TYPES:
        # really we need to return an exec-ed-capable client
        return None
    if course_type in OPEN_COURSES_COURSE_TYPES:
        # return an edx-enterprise client
        return None
    return None
    """
    raise NotImplementedError
