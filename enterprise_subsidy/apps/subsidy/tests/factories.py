"""
Test factories for subsidy models.
"""
import random
from datetime import timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import factory
from factory.fuzzy import FuzzyText
from faker import Faker
from openedx_ledger.models import UnitChoices

from enterprise_subsidy.apps.core.models import User
from enterprise_subsidy.apps.subsidy.models import (
    EnterpriseSubsidyFeatureRole,
    EnterpriseSubsidyRoleAssignment,
    RevenueCategoryChoices,
    Subsidy,
    SubsidyReferenceChoices
)

USER_PASSWORD = 'password'

FAKER = Faker()


def fake_datetime(is_future=False):
    """ Helper to get past or future localized datetime with microseconds. """
    delta = timedelta(microseconds=random.randint(0, 999999))
    if is_future:
        return FAKER.future_datetime(tzinfo=ZoneInfo("UTC")) + delta
    return FAKER.past_datetime(tzinfo=ZoneInfo("UTC")) + delta


class SubsidyFactory(factory.django.DjangoModelFactory):
    """
    Test factory for the `Subsidy` model.
    """
    class Meta:
        model = Subsidy

    uuid = factory.LazyFunction(uuid4)
    starting_balance = factory.Faker("random_int", min=10000, max=1000000)
    unit = UnitChoices.USD_CENTS
    reference_id = factory.Faker("lexify", text="????????")
    reference_type = SubsidyReferenceChoices.SALESFORCE_OPPORTUNITY_LINE_ITEM
    enterprise_customer_uuid = factory.LazyFunction(uuid4)
    active_datetime = factory.LazyFunction(fake_datetime)
    expiration_datetime = factory.LazyFunction(lambda: fake_datetime(is_future=True))
    revenue_category = RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY
    internal_only = False
    title = factory.Faker("sentence")
    is_soft_deleted = False

    @classmethod
    def to_dict(cls):
        """
        Return a dict of the subsidy.
        """
        return factory.build(dict, FACTORY_CLASS=SubsidyFactory)

    @classmethod
    def to_default_fields_dict(cls):
        """
        Return a dict of the subsidy with default values.
        """
        base_dict = factory.build(dict, FACTORY_CLASS=SubsidyFactory)
        return {f"default_{key}" if key != "reference_id" else key: value for key, value in base_dict.items()}


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
