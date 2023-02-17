"""
Test factories for subsidy models.
"""
import datetime
from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText
from faker import Faker

from enterprise_subsidy.apps.core.models import User
from enterprise_subsidy.apps.subsidy.models import EnterpriseSubsidyFeatureRole, EnterpriseSubsidyRoleAssignment

USER_PASSWORD = 'password'


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.Faker('user_name')
    password = factory.PostGenerationMethodCall('set_password', USER_PASSWORD)
    email = factory.Faker('email')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True
    is_staff = False
    is_superuser = False

    class Meta:
        model = User


class EnterpriseSubsidyFeatureRoleFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseSubsidyFeatureRole` model.
    """
    name = FuzzyText(length=32)

    class Meta:
        model = EnterpriseSubsidyFeatureRole


class EnterpriseSubsidyRoleAssignmentFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseSubisydRoleAssignment` model.
    """
    role = factory.SubFactory(EnterpriseSubsidyFeatureRoleFactory)
    enterprise_id = factory.LazyFunction(uuid4)

    class Meta:
        model = EnterpriseSubsidyRoleAssignment
