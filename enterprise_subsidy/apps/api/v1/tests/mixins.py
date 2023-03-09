"""
Broadly-useful mixins for use in REST API tests.
"""
import uuid

from django.test.client import RequestFactory
from edx_rest_framework_extensions.auth.jwt.cookies import jwt_cookie_name
from edx_rest_framework_extensions.auth.jwt.tests.utils import generate_jwt_token, generate_unversioned_payload
from rest_framework.test import APITestCase

from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    SYSTEM_ENTERPRISE_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_LEARNER_ROLE,
    SYSTEM_ENTERPRISE_OPERATOR_ROLE
)
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyFeatureRole, EnterpriseSubsidyRoleAssignment
from enterprise_subsidy.apps.subsidy.tests.factories import (
    USER_PASSWORD,
    EnterpriseSubsidyRoleAssignmentFactory,
    UserFactory
)

STATIC_LMS_USER_ID = 999


class JwtMixin():
    """ Mixin with JWT-related helper functions. """
    def get_request_with_current_jwt_cookie(self):
        """
        Craft a request object with the current JWT cookie.
        """
        request = RequestFactory().get('/')
        request.COOKIES[jwt_cookie_name()] = self.client.cookies[jwt_cookie_name()].value
        return request

    def _jwt_token_from_role_context_pairs(self, role_context_pairs):
        """
        Generates a new JWT token with roles assigned from pairs of (role name, context).
        """
        roles = []
        for role, context in role_context_pairs:
            role_data = f'{role}'
            if context is not None:
                role_data += f':{context}'
            roles.append(role_data)

        payload = generate_unversioned_payload(self.user)
        payload.update({'roles': roles})
        payload.update({
            'user_id': STATIC_LMS_USER_ID,
        })
        return generate_jwt_token(payload)

    def set_jwt_cookie(self, role_context_pairs=None):
        """
        Set jwt token in cookies
        """
        jwt_token = self._jwt_token_from_role_context_pairs(role_context_pairs or [])
        self.client.cookies[jwt_cookie_name()] = jwt_token


class APITestMixin(JwtMixin, APITestCase):
    """
    Mixin for functions shared between different API test classes
    """

    def setUp(self):
        super().setUp()
        self.enterprise_uuid = str(uuid.uuid4())
        self.enterprise_name = 'Test Enterprise'
        self.enterprise_slug = 'test-enterprise'
        self.desired_system_wide_role = None
        self.desired_feature_role = None

    def set_up_admin(self, enterprise_uuids=None):
        """
        Helper for setting up a user and assigning the staff role.
        """
        self.desired_system_wide_role = SYSTEM_ENTERPRISE_ADMIN_ROLE
        self.desired_feature_role = ENTERPRISE_SUBSIDY_ADMIN_ROLE
        self.set_up_user_with_assignments(is_staff=True, enterprise_uuids=enterprise_uuids)

    def set_up_learner(self, enterprise_uuids=None):
        """
        Helper for setting up a user and assigning the learner role.  By default,
        assigns the learner roles for self.enterprise_uuid in the JWT roles
        and DB assignments.
        """
        self.desired_system_wide_role = SYSTEM_ENTERPRISE_LEARNER_ROLE
        self.desired_feature_role = ENTERPRISE_SUBSIDY_LEARNER_ROLE
        self.set_up_user_with_assignments(is_staff=False, enterprise_uuids=enterprise_uuids)

    def set_up_operator(self):
        """
        Helper for setting up a user and assigning the operator role.
        """
        self.desired_system_wide_role = SYSTEM_ENTERPRISE_OPERATOR_ROLE
        self.desired_feature_role = ENTERPRISE_SUBSIDY_OPERATOR_ROLE
        self.set_up_user_with_assignments(is_staff=True)

    def set_up_user_with_assignments(self, is_staff=False, enterprise_uuids=None):
        """
        Helper for setting up a basic user with implicit and explicit role assignments.
        """
        self.set_up_user(is_staff=is_staff)
        self.assign_implicit_jwt_system_wide_role(
            system_wide_role=self.desired_system_wide_role,
            jwt_contexts=enterprise_uuids,
        )
        self.assign_explicit_db_feature_role(
            feature_role=self.desired_feature_role,
            enterprise_uuids=enterprise_uuids,
        )

    def set_up_user(self, is_staff=False):
        """
        Helper for setting up a basic user with no role assignments.
        """
        self.user = UserFactory(is_staff=is_staff)
        self.client.login(username=self.user.username, password=USER_PASSWORD)

    def assign_explicit_db_feature_role(self, user=None, feature_role=None, enterprise_uuids=None):
        """
        Assign the given feature role explicitly by creatin an ``EnterpriseSubsidyRoleAssignment`` DB object.
        """
        self.role = EnterpriseSubsidyFeatureRole.objects.get(name=feature_role)

        if not enterprise_uuids:
            enterprise_uuids = [self.enterprise_uuid]

        for enterprise_uuid in enterprise_uuids:
            self.role_assignment = EnterpriseSubsidyRoleAssignmentFactory(
                role=self.role,
                user=user or self.user,
                enterprise_id=enterprise_uuid,
            )

    def assign_implicit_jwt_system_wide_role(self, system_wide_role=None, jwt_contexts=None):
        """
        Assign the given system-wide role implicitly by creating a JWT token.
        """
        if not system_wide_role:
            system_wide_role = self.desired_system_wide_role
        if not jwt_contexts:
            jwt_contexts = [self.enterprise_uuid]

        self.set_jwt_cookie([(system_wide_role, jwt_context) for jwt_context in jwt_contexts])

    def remove_explicit_db_feature_role(self):
        """
        Remove any existing ``EnterpriseSubsidyRoleAssignment`` objects providing explicit grants.

        This is useful for testing implicit (JWT) access.
        """
        EnterpriseSubsidyRoleAssignment.objects.all().delete()

    def remove_implicit_jwt_system_wide_role(self):
        """
        Invalidate JWT cookie providing implicit grants.

        This is useful for testing explicit (DB) access.
        """
        self.set_jwt_cookie([('invalid_role', None)])
