"""
Test factories for subsidy models.
"""
from uuid import uuid4

import factory
from factory.fuzzy import FuzzyText
from openedx_ledger.models import UnitChoices
from openedx_ledger.test_utils.factories import LedgerFactory

from enterprise_subsidy.apps.core.models import User
from enterprise_subsidy.apps.subsidy.models import (
    EnterpriseSubsidyFeatureRole,
    EnterpriseSubsidyRoleAssignment,
    Subsidy,
    SubsidyReferenceChoices
)

USER_PASSWORD = 'password'


class SubsidyFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Subsidy` model.
    """
    class Meta:
        model = Subsidy

    uuid = factory.LazyFunction(uuid4)
    starting_balance = factory.Faker("random_int", min=10000, max=1000000)
    # ledger = factory.SubFactory(LedgerFactory)
    unit = UnitChoices.USD_CENTS
    reference_id = factory.Faker("lexify", text="????????")
    reference_type = SubsidyReferenceChoices.OPPORTUNITY_PRODUCT_ID
    enterprise_customer_uuid = factory.LazyFunction(uuid4)
    active_datetime = factory.Faker("past_datetime")
    expiration_datetime = factory.Faker("future_datetime")

    # Register hook to seed initial value for this test subsidy.
    # initialize_ledger = factory.PostGenerationMethodCall("initialize_ledger")


class UserFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `User` model.
    """
    class Meta:
        model = User

    username = factory.Faker('user_name')
    password = factory.PostGenerationMethodCall('set_password', USER_PASSWORD)
    email = factory.Faker('email')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    is_active = True
    is_staff = False
    is_superuser = False


class EnterpriseSubsidyFeatureRoleFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseSubsidyFeatureRole` model.
    """
    class Meta:
        model = EnterpriseSubsidyFeatureRole

    name = FuzzyText(length=32)


class EnterpriseSubsidyRoleAssignmentFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `EnterpriseSubisydRoleAssignment` model.
    """
    class Meta:
        model = EnterpriseSubsidyRoleAssignment

    role = factory.SubFactory(EnterpriseSubsidyFeatureRoleFactory)
    enterprise_id = factory.LazyFunction(uuid4)
