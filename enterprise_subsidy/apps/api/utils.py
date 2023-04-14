"""
Utility functions used in implemention of the REST API.
"""
from enterprise_subsidy.apps.subsidy.api import get_subsidy_by_uuid


def get_subsidy_customer_uuid_from_view(request, subsidy_uuid):
    """
    Used as the ``fn`` kwarg for the edx-rbac ``permission_required`` decorator.
    It wraps a view function that takes a request object and subsidy_uuid as parameters
    and, for the requested subsidy, returns a string form of the associated
    enterprise customer uuid.
    Returns None if no corresponding Subsidy record can be found.
    """
    subsidy = get_subsidy_by_uuid(subsidy_uuid)
    if subsidy:
        return str(subsidy.enterprise_customer_uuid)
    return None
