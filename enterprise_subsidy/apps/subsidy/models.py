"""
Model definitions for the subsidy app.

Some defintions:
* `ledger`: A running “list” of transactions that record the movement of value in and out of a subsidy.
* `stored value`:
      Value, in the form of a subscription license (denominated in “seats”) or learner credit (denominated in either
      USD or "seats"), stored in a ledger, which may be applied toward the cost of some content.
* `redemption`: The act of redeeming stored value for content.
"""
import logging
from datetime import datetime, timezone
from unittest import mock
from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils.functional import cached_property
from edx_rbac.models import UserRole, UserRoleAssignment
from edx_rbac.utils import ALL_ACCESS_CONTEXT
from model_utils.models import TimeStampedModel
from openedx_ledger import api as ledger_api
from openedx_ledger.models import Ledger, TransactionStateChoices, UnitChoices
from openedx_ledger.utils import create_idempotency_key_for_transaction
from requests.exceptions import HTTPError
from rest_framework import status
from simple_history.models import HistoricalRecords

from enterprise_subsidy.apps.api_client.enterprise import EnterpriseApiClient
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler

MOCK_CATALOG_CLIENT = mock.MagicMock()
MOCK_ENROLLMENT_CLIENT = mock.MagicMock()
MOCK_SUBSCRIPTION_CLIENT = mock.MagicMock()

# TODO: hammer this out.  Do we want this to be the name of a joinable table name?  Do we want it to reflect the field
# name of the response from the enrollment API?
OCM_ENROLLMENT_REFERENCE_TYPE = "enterprise_fufillment_source_uuid"


logger = logging.getLogger(__name__)


class ContentNotFoundForCustomerException(Exception):
    """
    Raise this when the given content_key is not in any catalog for this customer.
    """


class SubsidyReferenceChoices:
    """
    Enumerate different choices for the type of object that the subsidy's reference_id points to.  This is the type of
    object that caused the subsidy to come into existence.
    """
    SALESFORCE_OPPORTUNITY_LINE_ITEM = "salesforce_opportunity_line_item"
    CHOICES = (
        (SALESFORCE_OPPORTUNITY_LINE_ITEM, "Salesforce OpportunityLineItem (i.e. Opportunity Product)"),
    )


class RevenueCategoryChoices:
    """
    Enumerate different choices for the type of Subsidy.  For example, this can be used to control whether enrollments
    associated with this Subsidy should be rev rec'd through our standard commercial process or not.
    """
    BULK_ENROLLMENT_PREPAY = 'bulk-enrollment-prepay'
    PARTNER_NO_REV_PREPAY = 'partner-no-rev-prepay'
    CHOICES = (
        # TODO: do we have better human-readable names for these?
        (BULK_ENROLLMENT_PREPAY, 'bulk-enrollment-prepay'),
        (PARTNER_NO_REV_PREPAY, 'partner-no-rev-prepay'),
    )


def now():
    return datetime.now(timezone.utc)


class Subsidy(TimeStampedModel):
    """
    Subsidy model, specifically supporting Learner Credit type of subsidies.

    TODO: need a hook from enterprise-access that tells the subsidy when a request has been approved, so that we can
          _create_redemption() on the subsidy.  Additionally, we'd want a hook for request denials to avoid duplicating
          work, etc.

    .. no_pii:
    """

    class Meta:
        """
        Metaclass for Subsidy.
        """
        constraints = [
            models.UniqueConstraint(
                condition=Q(internal_only=False),  # Allow more flexibility for internal/test subsidies.
                fields=["reference_id", "reference_type"],
                name="unique_reference_id_non_internal",
            )
        ]

    # Please reserve the "subsidy_type" field name for the future when we use it to distinguish between
    # LearnerCreditSubsidy vs. SubscriptionSubsidy.
    #
    # subsidy_type = models.CharField(max_length=64, editable=False)

    uuid = models.UUIDField(
        primary_key=True,
        default=uuid4,
        editable=False,
        unique=True,
    )
    # `title` can be useful for downstream revenue recognition, and for a more convenient identifier.  It is intended to
    # be provided by ECS during the process of creating the Subsidy object.
    title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="A human-readable title decided by the staff that is provisioning this Subisdy for the customer."
    )
    starting_balance = models.BigIntegerField(
        null=False,
        blank=False,
        help_text="The positive balance this Subidy will be initially provisioned to start with."
    )
    ledger = models.OneToOneField(
        Ledger,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="The one Ledger uniquely associated with this Subsidy."
    )
    unit = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=UnitChoices.CHOICES,
        default=UnitChoices.USD_CENTS,
        db_index=True,
        help_text="Unit of currency used for all values of quantity for this Subsidy and associated transactions."
    )
    reference_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text=(
            "Identifier of the upstream Salesforce object that represents the deal that led to the creation of this "
            "Subsidy."
        ),
    )
    reference_type = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=SubsidyReferenceChoices.CHOICES,
        default=SubsidyReferenceChoices.SALESFORCE_OPPORTUNITY_LINE_ITEM,
        db_index=True,
        help_text=(
            "The type of object identified by the <code>reference_id</code> field.  Likely to be a type of Salesforce "
            "object."
        ),
    )
    enterprise_customer_uuid = models.UUIDField(
        blank=False,
        null=False,
        db_index=True,
        help_text="UUID of the enterprise customer assigned this Subsidy.",
    )
    internal_only = models.BooleanField(
        blank=False,
        null=False,
        default=False,
        help_text="If set, this subsidy will not be customer facing, nor have any influence on enterprise customers.",
    )
    revenue_category = models.CharField(
        max_length=255,
        blank=False,
        null=False,
        choices=RevenueCategoryChoices.CHOICES,
        default=RevenueCategoryChoices.BULK_ENROLLMENT_PREPAY,
        help_text=(
            'Control how revenue is recognized for subsidized enrollments.  In spirit, this is equivalent to the '
            '"Cataloge Category" for Coupons.  This field is only used downstream analytics and does not change any '
            'business logic.'
        ),
    )
    active_datetime = models.DateTimeField(
        null=True,
        default=None,
        help_text="The datetime when this Subsidy is considered active.  If null, this Subsidy is considered active."
    )
    expiration_datetime = models.DateTimeField(
        null=True,
        default=None,
        help_text="The datetime when this Subsidy is considered expired.  If null, this Subsidy is considered active."
        )
    history = HistoricalRecords()

    @cached_property
    def enterprise_client(self):
        """
        Get a client for accessing the Enterprise API (edx-enterprise endpoints via edx-platform).  This contains
        funcitons used for enrolling learners in OCM courses.  Cached to reduce the chance of repeated calls to auth.
        """
        return EnterpriseApiClient()

    def content_metadata_api(self):
        """
        API layer for interacting with enterprise catalog content metadata
        """
        return ContentMetadataApi()

    def geag_fulfillment_handler(self):
        """
        API layer for interacting with GEAG Fulfillment logic
        """
        return GEAGFulfillmentHandler()

    def price_for_content(self, content_key):
        """
        Return the price of the given content in USD Cents.

        Returns:
            int: Price of content in USD cents.

        Raises:
            ContentNotFoundForCustomerException:
                The given content_key is not in any catalog for the customer associated with this subsidy.
        """
        try:
            return self.content_metadata_api().get_course_price(self.enterprise_customer_uuid, content_key)
        except HTTPError as exc:
            if exc.response.status_code == status.HTTP_404_NOT_FOUND:
                raise ContentNotFoundForCustomerException(
                    'The given content_key is not in any catalog for this customer.'
                ) from exc
            raise

    def current_balance(self):
        return self.ledger.balance()

    def create_transaction(
        self,
        idempotency_key,
        quantity,
        lms_user_id=None,
        content_key=None,
        subsidy_access_policy_uuid=None,
        **transaction_metadata
    ):
        """
        Create a new Ledger Transaction and commit it to the database with a "created" state.

        Raises:
            openedx_ledger.models.LedgerLockAttemptFailed:
                Raises this if there's another attempt in process to add a transaction to this Ledger.
            openedx_ledger.api.LedgerBalanceExceeded:
                Raises this if the transaction would cause the balance of the ledger to become negative.
        """
        return ledger_api.create_transaction(
            ledger=self.ledger,
            quantity=quantity,
            idempotency_key=idempotency_key,
            lms_user_id=lms_user_id,
            content_key=content_key,
            subsidy_access_policy_uuid=subsidy_access_policy_uuid,
            **transaction_metadata,
        )

    def commit_transaction(self, ledger_transaction, fulfillment_identifier=None, external_reference=None):
        """
        Finalize a Ledger Transaction by populating the fulfillment_identifier (from the platform enrollment
        request) and transitioning its state to "committed".

        TODO: Shouldn't we require a fulfillment_identifier in some cases?  Maybe when the transaction
        doesn't have an "initial" key in the metadata?
        """
        logger.info(
            f'Committing transaction {ledger_transaction.uuid} with '
            f'fulfillment identifier {fulfillment_identifier} '
            f'and external_reference {external_reference}'
        )
        if fulfillment_identifier:
            ledger_transaction.fulfillment_identifier = fulfillment_identifier
        if external_reference:
            ledger_transaction.external_reference.set([external_reference])
        ledger_transaction.state = "committed"
        ledger_transaction.state = TransactionStateChoices.COMMITTED
        ledger_transaction.save()

    def rollback_transaction(self, ledger_transaction):
        """
        Progress the transaction to a failed state.
        """
        logger.info(f'Setting transaction {ledger_transaction.uuid} state to failed.')
        ledger_transaction.state = TransactionStateChoices.FAILED
        ledger_transaction.save()

    def redeem(self, lms_user_id, content_key, subsidy_access_policy_uuid, idempotency_key=None, metadata=None):
        """
        Redeem this subsidy and enroll the learner.

        This is a get_or_create type of function, so it is idempotent.  It also checks if the the content is redeemable
        by the learner.

        Returns:
            tuple(openedx_ledger.models.Transaction, bool):
                The first tuple element is a ledger transaction related to the redemption, or None if the subsidy is not
                redeemable for the given content.  The second element of the tuple is True if a Transaction was created
                as part of this request.

        Raises:
            openedx_ledger.models.LedgerLockAttemptFailed:
                Raises this if there's another attempt in process to add a transaction to this Ledger.
            Exception:
                All other exceptions raised during the creation of an enrollment.  This should have already triggered
                the rollback of a pending transaction.
        """
        if existing_transaction := self.get_redemption(lms_user_id, content_key):
            return (existing_transaction, False)

        is_redeemable, content_price = self.is_redeemable(content_key)
        if not is_redeemable:
            logger.info(
                f'{self} cannot redeem {content_key} with price {content_price} '
                f'for user {lms_user_id} in policy {subsidy_access_policy_uuid}'
            )
            return (None, False)
        try:
            transaction = self._create_redemption(
                lms_user_id,
                content_key,
                subsidy_access_policy_uuid,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        except ledger_api.LedgerBalanceExceeded:
            logger.info(
                f'{self} cannot redeem {content_key} with price {content_price} '
                f'for user {lms_user_id} in policy {subsidy_access_policy_uuid}. '
                f'This would have exceeded the ledger balance.'
            )
            return (None, False)
        if transaction:
            return (transaction, True)
        else:
            logger.info(
                f'{self} could not redeem {content_key} with price {content_price} '
                f'for user {lms_user_id} in policy {subsidy_access_policy_uuid}'
                f'Reached end of redeem attempt and the transaction object was falsey.'
            )
            return (None, False)

    def _create_redemption(
            self,
            lms_user_id,
            content_key,
            subsidy_access_policy_uuid,
            idempotency_key=None,
            metadata=None
    ):
        """
        Synchronously and idempotently enroll the learner in the content and record it in the Ledger.

        Two side-effects:
        * An enrollment or an entitlement is created in the target system (with metadata that links back to the ledger
          transaction ID).  The learner is able to access the requested content.
        * A Transaction is created in the Ledger associated with this subsidy, with state set to `committed` (and a
          reference_id set to the enrollment_id).

        After this function returns, either both of the two side-effects are fulfilled, *or neither*.

        Possible failure cases:
        * The enrollment fails to become created, returning a non-2xx error back to the subsidy service.  We should not
          commit a ledger transaction, but it's not outside the realm of possibilities that the enrollment has been
          *partially provisioned* in the target LMS. A partially provisioned enrollment is acceptable as long as the
          content remains inaccessible, and it can still be re-provisioned idempotently.
        * The enrollment succeeds, links a ledger transaction ID, returns a 2xx response to the subsidy app, but before
          the app receives the response, either the network connection is interrupted, or the subsidy app crashes.  This
          failure mode must be remedied asynchronously via corrective policies:
          https://github.com/openedx/enterprise-subsidy/blob/main/docs/decisions/0003-fulfillment-and-corrective-policies.rst#decision

        Bi-directional linking: Subclass implementations MUST also maintain bi-directional linking between the
        transaction record and the enrollment record.  The Transaction model provides a `reference_id` field for this
        purpose.

        Raises:
            openedx_ledger.models.LedgerLockAttemptFailed:
                Raises this if there's another attempt in process to add a transaction to this Ledger.
            openedx_ledger.api.LedgerBalanceExceeded:
                Raises this if the transaction would cause the balance of the ledger to become negative.
            Exception:
                All other exceptions raised during the creation of an enrollment.  This should have already triggered
                the rollback of a pending transaction.
        """
        quantity = -1 * self.price_for_content(content_key)
        if not idempotency_key:
            idempotency_key = create_idempotency_key_for_transaction(
                self.ledger,
                quantity,
                lms_user_id=lms_user_id,
                content_key=content_key,
                subsidy_access_policy_uuid=subsidy_access_policy_uuid,
            )
        tx_metadata = metadata or {}
        ledger_transaction = self.create_transaction(
            idempotency_key,
            quantity,
            content_key=content_key,
            lms_user_id=lms_user_id,
            subsidy_access_policy_uuid=subsidy_access_policy_uuid,
            **tx_metadata,
        )

        # Progress the transaction to a pending state to indicate that we're now attempting enrollment.
        ledger_transaction.state = TransactionStateChoices.PENDING
        ledger_transaction.save()

        try:
            if self.geag_fulfillment_handler().can_fulfill(ledger_transaction):
                self.geag_fulfillment_handler().fulfill(ledger_transaction)
        except Exception as exc:
            logger.exception(
                f'Failed to fulfill transaction {ledger_transaction.uuid} with the GEAG handler.'
            )
            self.rollback_transaction(ledger_transaction)
            raise exc

        try:
            enterprise_fulfillment_uuid = self.enterprise_client.enroll(lms_user_id, content_key, ledger_transaction)
            self.commit_transaction(
                ledger_transaction,
                fulfillment_identifier=enterprise_fulfillment_uuid,
            )
        except Exception as exc:
            logger.exception(
                f'Failed to enroll for transaction {ledger_transaction.uuid} via the enterprise client.'
            )
            self.rollback_transaction(ledger_transaction)
            raise exc

        return ledger_transaction

    def is_redeemable(self, content_key):
        """
        Check if this subsidy is redeemable (by anyone) at a given time.

        Is there enough stored value in this subsidy's ledger to redeem for the cost of the given content?

        Args:
            content_key (str): content key of content we may try to redeem.
            redemption_datetime (datetime.datetime): The point in time to check for redemability.

        Returns:
            2-tuple of (bool: True if redeemable, int: price of content)
        """
        content_price = self.price_for_content(content_key)
        redeemable = False
        if content_price is not None:
            redeemable = self.current_balance() >= content_price
        return redeemable, content_price

    def get_redemption(self, lms_user_id, content_key):
        """
        Return the committed transaction representing this redemption,
        or None if no such transaction exists.

        Args:
            lms_user_id (str): The learner of the redemption to check.
            content_key (str): The content of the redemption to check.

        Returns:
            openedx_ledger.models.Transaction: a ledger transaction representing the redemption.
        """
        return self.transactions_for_learner_and_content(lms_user_id, content_key).filter(
            state=TransactionStateChoices.COMMITTED,
        ).first()

    def all_transactions(self):
        return self.ledger.transactions.select_related(
            'reversal',
        )

    def transactions_for_learner(self, lms_user_id):
        return self.all_transactions().filter(lms_user_id=lms_user_id)

    def transactions_for_content(self, content_key):
        return self.all_transactions().filter(content_key=content_key)

    def transactions_for_learner_and_content(self, lms_user_id, content_key):
        return self.all_transactions().filter(
            lms_user_id=lms_user_id,
            content_key=content_key,
        )

    def __str__(self):
        return f'<Subsidy uuid={self.uuid}, title={self.title}>'


#
# Two edx-rbac supporting models follows.
#
class EnterpriseSubsidyFeatureRole(UserRole):
    """
    User role definitions specific to Enterprise Subsidy.

     .. no_pii:
    """

    def __str__(self):
        """
        Return human-readable string representation.
        """
        return f"EnterpriseSubsidyFeatureRole(name={self.name})"

    def __repr__(self):
        """
        Return uniquely identifying string representation.
        """
        return self.__str__()


class EnterpriseSubsidyRoleAssignment(UserRoleAssignment):
    """
    Model to map users to an EnterpriseSubsidyFeatureRole.

     .. no_pii:
    """

    role_class = EnterpriseSubsidyFeatureRole
    enterprise_id = models.UUIDField(blank=True, null=True, verbose_name='Enterprise Customer UUID')

    def get_context(self):
        """
        Generate an access context string for this assignment.

        Returns:
            str: The enterprise customer UUID or `*` if the user has access to all resources.
        """
        if self.enterprise_id:
            # converting the UUID('ee5e6b3a-069a-4947-bb8d-d2dbc323396c') to 'ee5e6b3a-069a-4947-bb8d-d2dbc323396c'
            return str(self.enterprise_id)
        return ALL_ACCESS_CONTEXT

    @classmethod
    def user_assignments_for_role_name(cls, user, role_name):
        """
        Find assignments for a given user and role name.
        """
        return cls.objects.filter(user__id=user.id, role__name=role_name)

    def __str__(self):
        """
        Human-readable string representation.
        """
        # pylint: disable=no-member
        return f"EnterpriseSubsidyRoleAssignment(name={self.role.name}, user={self.user.id})"

    def __repr__(self):
        """
        Human-readable string representation.
        """
        return self.__str__()
