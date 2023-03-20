"""
Rules needed to restrict access to the enterprise subsidy service.
"""
import crum
import rules
from edx_rbac.utils import request_user_has_implicit_access_via_jwt, user_has_access_via_database
from edx_rest_framework_extensions.auth.jwt.authentication import get_decoded_jwt_from_auth
from edx_rest_framework_extensions.auth.jwt.cookies import get_decoded_jwt

from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    PERMISSION_CAN_CREATE_TRANSACTIONS,
    PERMISSION_CAN_READ_CONTENT_METADATA,
    PERMISSION_CAN_READ_SUBSIDIES,
    PERMISSION_CAN_READ_TRANSACTIONS
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyRoleAssignment


def _user_has_explicit_access_via_feature_role(user, context, feature_role):
    """
    Check that the given user has explicit access to the given context via the given feature_role.

    Returns:
        bool: True if the user has access.
    """
    if not context:
        return False
    return user_has_access_via_database(
        user,
        feature_role,
        EnterpriseSubsidyRoleAssignment,
        context,
    )


def _user_has_implicit_access_via_feature_role(user, context, feature_role):  # pylint: disable=unused-argument
    """
    Check that the requesting user has implicit access to the given context via the given feature role.

    Returns:
        bool: True if the user has access.
    """
    if not context:
        return False
    request = crum.get_current_request()
    decoded_jwt = get_decoded_jwt(request) or get_decoded_jwt_from_auth(request)
    return request_user_has_implicit_access_via_jwt(
        decoded_jwt,
        feature_role,
        context,
    )


@rules.predicate
def has_implicit_access_to_subsidy_operator(user, context):
    return _user_has_implicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_OPERATOR_ROLE)


@rules.predicate
def has_explicit_access_to_subsidy_operator(user, context):
    return _user_has_explicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_OPERATOR_ROLE)


@rules.predicate
def has_implicit_access_to_subsidy_admin(user, context):
    return _user_has_implicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_ADMIN_ROLE)


@rules.predicate
def has_explicit_access_to_subsidy_admin(user, context):
    return _user_has_explicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_ADMIN_ROLE)


@rules.predicate
def has_implicit_access_to_subsidy_learner(user, context):
    return _user_has_implicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_LEARNER_ROLE)


@rules.predicate
def has_explicit_access_to_subsidy_learner(user, context):
    return _user_has_explicit_access_via_feature_role(user, context, ENTERPRISE_SUBSIDY_LEARNER_ROLE)


# Now, recombine the implicit and explicit rules for a given feature role using composition.  Also, waterfall the rules
# by defining access levels which give "higher" levels access to their own level, as well as everything below.
# pylint: disable=unsupported-binary-operation
has_learner_level_access = (
    has_implicit_access_to_subsidy_operator | has_explicit_access_to_subsidy_operator |
    has_implicit_access_to_subsidy_admin | has_explicit_access_to_subsidy_admin |
    has_implicit_access_to_subsidy_learner | has_explicit_access_to_subsidy_learner
)
# pylint: disable=unsupported-binary-operation
has_admin_level_access = (
    has_implicit_access_to_subsidy_operator | has_explicit_access_to_subsidy_operator |
    has_implicit_access_to_subsidy_admin | has_explicit_access_to_subsidy_admin
)
# pylint: disable=unsupported-binary-operation
has_operator_level_access = has_implicit_access_to_subsidy_operator | has_explicit_access_to_subsidy_operator


# Finally, grant specific permissions to the appropriate access level.
rules.add_perm(PERMISSION_CAN_CREATE_TRANSACTIONS, has_operator_level_access)
rules.add_perm(PERMISSION_CAN_READ_SUBSIDIES, has_admin_level_access)
rules.add_perm(PERMISSION_CAN_READ_TRANSACTIONS, has_learner_level_access)
rules.add_perm(PERMISSION_CAN_READ_CONTENT_METADATA, has_learner_level_access)
