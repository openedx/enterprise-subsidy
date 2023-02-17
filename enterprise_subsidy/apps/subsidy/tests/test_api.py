from uuid import UUID, uuid4

import mock
import pytest
from django.test import TestCase
from openedx_ledger import api as ledger_api
from openedx_ledger.models import UnitChoices

from enterprise_subsidy.apps.subsidy import api as subsidy_api


@pytest.fixture
def learner_credit_fixture():
    subsidy, _ = subsidy_api.get_or_create_learner_credit_subsidy(
        reference_id="test-opp-product-id",
        default_title="Test Learner Credit Subsidy",
        default_enterprise_customer_uuid=uuid4(),
        default_unit=UnitChoices.USD_CENTS,
        default_starting_balance=1000000,
    )
    return subsidy


@pytest.mark.django_db
def test_create_learner_credit_subsidy(learner_credit_fixture):
    """
    Test that a Subsidy, associated Ledger, and initial Transaction all got created successfully.  This can be easily
    confirmed by calling subsidy.current_balance() which reads all 3 related objects.
    """
    assert learner_credit_fixture.current_balance() == 1000000


@pytest.mark.django_db
def test_get_learner_credit_subsidy(learner_credit_fixture):
    """
    Test that a Subsidy can be retrieved, discarding supplied defaults.
    """
    subsidy, created = subsidy_api.get_or_create_learner_credit_subsidy(
        reference_id=learner_credit_fixture.reference_id,
        default_title="Default Title",
        default_enterprise_customer_uuid=uuid4(),
        default_unit=UnitChoices.USD_CENTS,
        default_starting_balance=30,
    )
    assert not created
    assert learner_credit_fixture.current_balance() == 1000000
