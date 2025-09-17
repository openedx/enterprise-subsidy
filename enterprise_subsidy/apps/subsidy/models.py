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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
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
from enterprise_subsidy.apps.api_client.lms_user import LmsUserApiClient
from enterprise_subsidy.apps.content_metadata.api import ContentMetadataApi
from enterprise_subsidy.apps.core import event_bus
from enterprise_subsidy.apps.core.utils import localized_utcnow
from enterprise_subsidy.apps.fulfillment.api import GEAGFulfillmentHandler, is_geag_fulfillment
from enterprise_subsidy.apps.fulfillment.exceptions import IncompleteContentMetadataException

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


class PriceValidationError(ValidationError):
    """
    Raised in cases related to requested prices, when the requested price
    fails our validation checks.
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


class ActiveSubsidyManager(models.Manager):
    """
    Custom manager for the Subsidy model that filters out soft-deleted subsidies.
    """
    def get_queryset(self):
        """
        Override the default queryset to filter out soft-deleted subsidies.
        """
        return super().get_queryset().filter(is_soft_deleted=False)


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
        ordering = ['-created']
        verbose_name = 'Subsidy'
        verbose_name_plural = 'Subsidies'

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
        help_text="The datetime when this Subsidy is considered active.  If null, this Subsidy is considered inactive."
    )
    expiration_datetime = models.DateTimeField(
        null=True,
        default=None,
        help_text="The datetime when this Subsidy is considered expired.  If null, this Subsidy is considered active."
        )
    is_soft_deleted = models.BooleanField(
        default=False,
        help_text="If set, this subsidy will be considered as soft-deleted or deactivated.",
        db_index=True,
    )
    history = HistoricalRecords()

    objects = ActiveSubsidyManager()
    all_objects = models.Manager()

    def clean(self):
        """
        Ensures that non-internal-only subsidies are unique
        on (reference_id, reference_type).  This is necessary
        because MySQL does not support conditional unique constraints.
        """
        if not self.internal_only:
            other_record = Subsidy.objects.filter(
                reference_id=self.reference_id,
                reference_type=self.reference_type,
            ).exclude(uuid=self.uuid).first()
            if other_record:
                raise ValidationError(
                    f'Subsidy {other_record.uuid} already exists with the same '
                    f'reference_id {self.reference_id} and reference_type {self.reference_type}'
                )

    def save(self, *args, **kwargs):
        """
        Overrides default save() method to run full_clean.
        """
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """
        Returns true if the localized current time is
        between ``active_datetime`` and ``expiration_datetime``.
        """
        return self.active_datetime <= localized_utcnow() <= self.expiration_datetime

    @cached_property
    def enterprise_client(self):
        """
        Get a client for accessing the Enterprise API (edx-enterprise endpoints via edx-platform).  This contains
        funcitons used for enrolling learners in OCM courses.  Cached to reduce the chance of repeated calls to auth.
        """
        return EnterpriseApiClient()

    def delete(self, *args, **kwargs):
        """
        Soft-delete this Subsidy by setting the `is_soft_deleted` flag to True.
        """
        self.is_soft_deleted = True
        self.save()

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

    def lms_user_client(self):
        """
        API layer for interacting with the LMS Account API
        """
        return LmsUserApiClient()

    def email_for_learner(self, lms_user_id):
        """
        Return the email associated with an LMS learner
        """
        user_data = self.lms_user_client().best_effort_user_data(lms_user_id)
        if isinstance(user_data, dict):
            return user_data.get('email')
        return None

    def metadata_summary_for_content(self, content_key):
        """
        Best effort return the metadata summary of the given content.

        Returns:
            dict: Metadata summary (or empty dict if there is a bug in our code).

        Raises:
            ContentNotFoundForCustomerException: If the metadata service returned 404.
        """
        content_summary = {}
        try:
            content_summary = self.content_metadata_api().get_content_summary(
                self.enterprise_customer_uuid,
                content_key
            )
        except HTTPError as exc:
            if exc.response.status_code == status.HTTP_404_NOT_FOUND:
                raise ContentNotFoundForCustomerException(
                    'The given content_key is not in any catalog for this customer.'
                ) from exc
        return content_summary

    def title_for_content(self, content_key):
        """
        Best effort return the title of the given content.

        Returns:
            string: Title of content or None.
        """
        return self.metadata_summary_for_content(content_key).get('content_title')

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

    @property
    def total_deposits(self):
        """
        Returns the sum of all value added to the subsidy.

        At the time of writing, this includes both deposits AND adjustments, as both are essentially meant to augment
        the value added to the subsidy.

        Returns:
            int: Sum of all value added to the subsidy, in USD cents.
        """
        return self.ledger.total_deposits()

    def create_transaction(
        self,
        idempotency_key,
        quantity,
        lms_user_id=None,
        lms_user_email=None,
        content_key=None,
        parent_content_key=None,
        content_title=None,
        course_run_start_date=None,
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
        ledger_transaction = ledger_api.create_transaction(
            ledger=self.ledger,
            quantity=quantity,
            idempotency_key=idempotency_key,
            lms_user_id=lms_user_id,
            lms_user_email=lms_user_email,
            content_key=content_key,
            parent_content_key=parent_content_key,
            content_title=content_title,
            course_run_start_date=course_run_start_date,
            subsidy_access_policy_uuid=subsidy_access_policy_uuid,
            **transaction_metadata,
        )
        event_bus.send_transaction_created_event(ledger_transaction)
        return ledger_transaction

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
        ledger_transaction.state = TransactionStateChoices.COMMITTED
        ledger_transaction.save()
        event_bus.send_transaction_committed_event(ledger_transaction)

    def rollback_transaction(self, ledger_transaction, external_transaction_reference=None):
        """
        Progress the transaction to a failed state. Also attempt to cancel any external fulfillments given.

        Args:
            ledger_transaction (openedx_ledger.models.Transaction):
                The transaction to rollback.
            external_transaction_reference (openedx_ledger.models.ExternalTransactionReference):
                The external fulfillment to cancel (optional). Must link back to the given transaction.

        Raises:
            I made a best effort to avoid raising an exception unless there's local database issues like locking or
            other read errors on transaction.save().
        """
        try:
            if external_transaction_reference and external_transaction_reference.transaction == ledger_transaction:
                logger.info(
                    '[rollback_transaction] Attempting to cancel external fulfillment %s for transaction %s.',
                    external_transaction_reference.external_reference_id,
                    ledger_transaction.uuid,
                )
                self.geag_fulfillment_handler().cancel_fulfillment(external_transaction_reference)
                logger.info(
                    '[rollback_transaction] Successfully canceled external fulfillment %s for transaction %s.',
                    external_transaction_reference.external_reference_id,
                    ledger_transaction.uuid,
                )
        except HTTPError as exc:
            logger.error(
                "[rollback_transaction] Error canceling external fulfillment %s: %s",
                external_transaction_reference.external_reference_id,
                exc,
            )
        except Exception as exc:  # pylint: disable=broad-except
            # We are extra sensitive to raising an exception from this method because it's already running inside a
            # rollback context, so the caller already knows something went wrong and is trying to recover.
            logger.error(
                "[rollback_transaction] Swallowing uncaught exception trying to cancel external fulfillment %s: %s",
                external_transaction_reference.external_reference_id,
                exc,
            )
        finally:
            # No matter what, we absolutely need to progress the transaction to a failed state.
            logger.info('[rollback_transaction] Setting transaction %s state to failed.', ledger_transaction.uuid)
            ledger_transaction.state = TransactionStateChoices.FAILED
            ledger_transaction.save()
            event_bus.send_transaction_failed_event(ledger_transaction)

    def redeem(
        self,
        lms_user_id,
        content_key,
        subsidy_access_policy_uuid,
        idempotency_key=None,
        requested_price_cents=None,
        metadata=None,
    ):
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
        if existing_transaction := self.get_committed_transaction_no_reversal(lms_user_id, content_key):
            return (existing_transaction, False)

        is_redeemable, content_price = self.is_redeemable(content_key, requested_price_cents)

        base_exception_msg = (
            f'{self} cannot redeem {content_key} with price {content_price} '
            f'for user {lms_user_id} in policy {subsidy_access_policy_uuid}. %s'
        )

        if not is_redeemable:
            logger.info(base_exception_msg, 'Not enough balance in the subsidy')
            return (None, False)
        try:
            lms_user_email = self.email_for_learner(lms_user_id)

            # Fetch one or more metadata keys from catalog service, with overall metadata request locally cached.
            content_metadata_summary = self.metadata_summary_for_content(content_key)
            content_title = content_metadata_summary.get('content_title')
            parent_content_key = content_metadata_summary.get('content_key')
            course_run_start_date = content_metadata_summary.get('course_run_start_date')

            transaction = self._create_redemption(
                lms_user_id,
                content_key,
                parent_content_key,
                content_price,
                subsidy_access_policy_uuid,
                lms_user_email=lms_user_email,
                content_title=content_title,
                course_run_start_date=course_run_start_date,
                idempotency_key=idempotency_key,
                metadata=metadata,
            )
        except ledger_api.LedgerBalanceExceeded:
            logger.exception(base_exception_msg, 'This would have exceeded the ledger balance.')
            return (None, False)
        except HTTPError as exc:
            logger.exception(base_exception_msg, 'HTTPError during enrollment.')
            # Because this error occurred when requesting an enrollment action in another service,
            # we raise instead of return, so that the subsidy API layer can pass more exception
            # info back to the caller.
            raise exc
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
            parent_content_key,
            content_price,
            subsidy_access_policy_uuid,
            content_title=None,
            lms_user_email=None,
            course_run_start_date=None,
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
        quantity = -1 * content_price
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
            parent_content_key=parent_content_key,
            content_title=content_title,
            course_run_start_date=course_run_start_date,
            lms_user_id=lms_user_id,
            lms_user_email=lms_user_email,
            subsidy_access_policy_uuid=subsidy_access_policy_uuid,
            **tx_metadata,
        )

        # Progress the transaction to a pending state to indicate that we're now attempting enrollment.
        ledger_transaction.state = TransactionStateChoices.PENDING
        ledger_transaction.save()

        external_transaction_reference = None
        if is_geag_fulfillment(ledger_transaction):
            try:
                if not self.geag_fulfillment_handler().can_fulfill(ledger_transaction):
                    raise IncompleteContentMetadataException(
                        f'Missing variant_id needed for GEAG transaction {ledger_transaction}, '
                        'not attempting fulfillment'
                    )

                external_transaction_reference = self.geag_fulfillment_handler().fulfill(ledger_transaction)
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
            self.rollback_transaction(ledger_transaction, external_transaction_reference)
            raise exc

        return ledger_transaction

    def validate_requested_price(self, content_key, requested_price_cents, canonical_price_cents):
        """
        Validates that the requested redemption price (in USD cents)
        is within some acceptable error bound interval.
        """
        if requested_price_cents < 0:
            raise PriceValidationError('Can only redeem non-negative content prices in cents.')

        lower_bound = settings.ALLOCATION_PRICE_VALIDATION_LOWER_BOUND_RATIO * canonical_price_cents
        upper_bound = settings.ALLOCATION_PRICE_VALIDATION_UPPER_BOUND_RATIO * canonical_price_cents
        if not (lower_bound <= requested_price_cents <= upper_bound):
            raise PriceValidationError(
                f'Requested price {requested_price_cents} for {content_key} '
                f'outside of acceptable interval on canonical course price of {canonical_price_cents}.'
            )

        return requested_price_cents

    def is_redeemable(self, content_key, requested_price_cents=None):
        """
        Check if this subsidy is redeemable (by anyone) at a given time.

        Is there enough stored value in this subsidy's ledger to redeem for the cost of the given content?

        Args:
            content_key (str): content key of content we may try to redeem.
            redemption_datetime (datetime.datetime): The point in time to check for redemability.
            requested_price_cents (int): An optional "override" price for the given content.
                 If present, we'll compare this quantity against the current balance,
                 instead of the price read from our catalog service.  An override *must*
                 be within some reasonable bound of the real price.

        Returns:
            2-tuple of (bool: True if redeemable, int: price of content)
        """
        canonical_price_cents = self.price_for_content(content_key)
        content_price = canonical_price_cents
        if requested_price_cents:
            content_price = self.validate_requested_price(
                content_key,
                requested_price_cents,
                canonical_price_cents,
            )

        redeemable = False
        if content_price is not None:
            redeemable = self.current_balance() >= content_price
        return redeemable, content_price

    def get_committed_transaction_no_reversal(self, lms_user_id, content_key):
        """
        Return the committed transaction without a reversal representing this redemption,
        or None if no such transaction exists.

        TODO: Also include transactions with non-committed reversals (reversal.state != "committed").  Right now, this
        defect has no real-world impact because we don't currently allow reversals to enter any non-committed state, but
        this defect is probably worth fixing if reversals can become non-committed.

        Args:
            lms_user_id (str): The learner of the redemption to check.
            content_key (str): The content of the redemption to check.

        Returns:
            openedx_ledger.models.Transaction: a ledger transaction representing the redemption.
        """
        return self.transactions_for_learner_and_content(lms_user_id, content_key).filter(
            state=TransactionStateChoices.COMMITTED,
            reversal__isnull=True,
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
        """
        Return all current and/or historical transactions representing the given user redeeming content.  Output may
        contain reversed transactions.
        """
        return self.all_transactions().filter(
            lms_user_id=lms_user_id,
            content_key=content_key,
        )

    def aggregated_enrollments_from_transactions(self, subsidy_access_policy_uuid=None):
        """
        Return aggregated number of all committed transactions without reversals grouped lms_user_id. Optionally
        filtered down further with a policy UUID.
        """
        # Fetch all transactions associated with the subsidy that have no reversals and are committed.
        relevant_transactions = self.all_transactions().filter(
            reversal__isnull=True,
            state=TransactionStateChoices.COMMITTED,
            lms_user_id__isnull=False,
        )
        # Further filter by a policy UUID if provided
        if subsidy_access_policy_uuid:
            relevant_transactions = relevant_transactions.filter(subsidy_access_policy_uuid=subsidy_access_policy_uuid)
        # Return the formatted aggregates
        return relevant_transactions.values('lms_user_id').annotate(total=models.Count('content_key'))

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
