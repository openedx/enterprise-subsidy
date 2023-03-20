"""
Tests for the edx-rbac rules predicates.
"""
import uuid
from unittest import mock

import ddt
from edx_rbac.utils import ALL_ACCESS_CONTEXT

from enterprise_subsidy.apps.api.v1.tests.mixins import APITestMixin
from enterprise_subsidy.apps.subsidy.constants import (
    PERMISSION_CAN_CREATE_TRANSACTIONS,
    PERMISSION_CAN_READ_SUBSIDIES,
    PERMISSION_CAN_READ_TRANSACTIONS
)


@ddt.ddt
class TestSubsidyAdminRBACPermissions(APITestMixin):
    """
    Test defined django rules for authorization checks.
    """
    def set_up_user_by_type(self, user_type, authentication_type, jwt_context_override=False):
        """ Inner helper for setting up JWT roles. """
        if user_type == "learner":
            self.set_up_learner()
        elif user_type == "admin":
            self.set_up_admin()
        elif user_type == "operator":
            self.set_up_operator()
        else:
            raise ValueError("invalid user_type")

        if jwt_context_override is not False:
            self.assign_implicit_jwt_system_wide_role(jwt_contexts=[jwt_context_override])

        if authentication_type == "implicit":
            self.remove_explicit_db_feature_role()
        elif authentication_type == "explicit":
            self.remove_implicit_jwt_system_wide_role()
        else:
            raise ValueError("invalid authentication_type")

    @mock.patch('enterprise_subsidy.apps.subsidy.rules.crum.get_current_request')
    @ddt.data(
        # user_type, authentication_type, permission,                         expected_has_perm
        ("learner",  "implicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("learner",  "explicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("admin",    "implicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("admin",    "explicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("operator", "implicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("operator", "explicit",          PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("learner",  "implicit",          PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("learner",  "explicit",          PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("admin",    "implicit",          PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("admin",    "explicit",          PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("operator", "implicit",          PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("operator", "explicit",          PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("learner",  "implicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("learner",  "explicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("admin",    "implicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("admin",    "explicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("operator", "implicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, True),
        ("operator", "explicit",          PERMISSION_CAN_CREATE_TRANSACTIONS, True),
    )
    @ddt.unpack
    def test_has_perm(self, user_type, authentication_type, permission, expected_has_perm, get_current_request_mock):
        self.set_up_user_by_type(user_type, authentication_type)
        get_current_request_mock.return_value = self.get_request_with_current_jwt_cookie()
        assert self.user.has_perm(permission, self.enterprise_uuid) == expected_has_perm

    @mock.patch('enterprise_subsidy.apps.subsidy.rules.crum.get_current_request')
    @ddt.data(
        # user_type, permission,                         expected_has_perm
        ("learner",  PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("admin",    PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("operator", PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("learner",  PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("admin",    PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("operator", PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("learner",  PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("admin",    PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("operator", PERMISSION_CAN_CREATE_TRANSACTIONS, False),
    )
    @ddt.unpack
    def test_has_perm_implicit_no_context(self, user_type, permission, expected_has_perm, get_current_request_mock):
        self.set_up_user_by_type(user_type, "implicit", jwt_context_override=None)
        get_current_request_mock.return_value = self.get_request_with_current_jwt_cookie()
        assert self.user.has_perm(permission, self.enterprise_uuid) == expected_has_perm

    @mock.patch('enterprise_subsidy.apps.subsidy.rules.crum.get_current_request')
    @ddt.data(
        # user_type, permission,                         expected_has_perm
        ("learner",  PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("admin",    PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("operator", PERMISSION_CAN_READ_TRANSACTIONS,   True),
        ("learner",  PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("admin",    PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("operator", PERMISSION_CAN_READ_SUBSIDIES,      True),
        ("learner",  PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("admin",    PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("operator", PERMISSION_CAN_CREATE_TRANSACTIONS, True),
    )
    @ddt.unpack
    def test_has_perm_implicit_all_access_context(
        self, user_type, permission, expected_has_perm, get_current_request_mock
    ):
        self.set_up_user_by_type(user_type, "implicit", jwt_context_override=ALL_ACCESS_CONTEXT)
        get_current_request_mock.return_value = self.get_request_with_current_jwt_cookie()
        assert self.user.has_perm(permission, self.enterprise_uuid) == expected_has_perm

    @mock.patch('enterprise_subsidy.apps.subsidy.rules.crum.get_current_request')
    @ddt.data(
        # user_type, permission,                         expected_has_perm
        ("learner",  PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("admin",    PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("operator", PERMISSION_CAN_READ_TRANSACTIONS,   False),
        ("learner",  PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("admin",    PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("operator", PERMISSION_CAN_READ_SUBSIDIES,      False),
        ("learner",  PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("admin",    PERMISSION_CAN_CREATE_TRANSACTIONS, False),
        ("operator", PERMISSION_CAN_CREATE_TRANSACTIONS, False),
    )
    @ddt.unpack
    def test_has_perm_implicit_incorrect_context(
        self, user_type, permission, expected_has_perm, get_current_request_mock
    ):
        self.set_up_user_by_type(user_type, "implicit", jwt_context_override=str(uuid.uuid4()))
        get_current_request_mock.return_value = self.get_request_with_current_jwt_cookie()
        assert self.user.has_perm(permission, self.enterprise_uuid) == expected_has_perm
