from uuid import UUID, uuid4

import mock
import pytest
from django.test import TestCase
from openedx_ledger import api as ledger_api
from openedx_ledger.models import UnitChoices

from enterprise_subsidy.apps.subsidy import api as subsidy_api


@pytest.fixture
def group_a():
    return {
        'uuid': uuid4(),
    }


@pytest.fixture
def catalog_a():
    return {
        'uuid': uuid4(),
    }


@pytest.fixture
def ledger_fixture():
    ledger_idp_key = uuid4()
    ledger = ledger_api.create_ledger(
        unit=UnitChoices.SEATS,
        idempotency_key=ledger_idp_key,
    )
    ledger_api.create_transaction(
        ledger,
        quantity=100,
        idempotency_key=f'ledger-{ledger_idp_key}-init-100',
    )
    return ledger


@pytest.fixture
def subscription_fixture():
    subsidy, _ = subsidy_api.get_or_create_subscription_subsidy(
        opportunity_id="test-opp-id",
        default_title="Test Subscription Subsidy",
        default_customer_uuid=uuid4(),
        default_unit=UnitChoices.SEATS,
        default_starting_balance=100,
        default_subscription_plan_uuid=uuid4(),
    )
    return subsidy


@pytest.fixture
def learner_credit_fixture():
    subsidy, _ = subsidy_api.get_or_create_learner_credit_subsidy(
        opportunity_id="test-opp-id",
        default_title="Test Learner Credit Subsidy",
        default_customer_uuid=uuid4(),
        default_unit=UnitChoices.USD_CENTS,
        default_starting_balance=1000000,
    )
    return subsidy


@pytest.mark.django_db
def test_create_subsidy_happy_path(subscription_fixture):
    assert subscription_fixture.unit == UnitChoices.SEATS


@pytest.mark.django_db
def test_subsidy_has_balance(subscription_fixture):
    assert subscription_fixture.unit == UnitChoices.SEATS
    subscription_fixture.subscription_client.get_plan_metadata.return_value = {
        'licenses': {'pending': 50, 'total': 100}
    }
    subsidy_api.sync_subscription(subscription_fixture, request_user='bob')
    # TODO: explain the subtlety that results in a "fresh" subscription balance being zero
    assert subscription_fixture.current_balance() == 0


@pytest.mark.django_db
def test_create_learner_credit_subsidy(learner_credit_fixture):
    assert learner_credit_fixture.current_balance() == 1000000
