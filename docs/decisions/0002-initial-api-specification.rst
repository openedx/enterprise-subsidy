0002 Initial API Specification
##############################

Status
******

**Accepted**

Context
*******

This doc describes the API specification for the ``enterprise-subsidy`` service.
Consider each chapter below a "decision".

Notable Implementation Details
==============================

- A reference to the policy that allowed a ledger transaction to be created
  should be written on the ledger transaction record.
  This is important in the context of a learner-credit access policy that
  has a spending cap imposed for the whole policy.
- The enterprise-subsidy service should always ask course-discovery for the current price of a piece of content
  before creating a ledger transaction, or when answering if a query about whether a ledger transaction
  can be written (i.e. "redeemability") for a given user/content combination. The course-discovery service is the content
  metadata source of truth and has certain compliance obligations, as does the enterprise-subsidy service.
  The enterprise-subsidy service may cache content price (or other metadata) for up to five minutes, as we expect
  that clients may use the service in such a way that 2 or 3 subsequent requests for price data may be made
  in a short amount of time. This should limit additional load placed on the course-discovery service from
  the enterprise-subsidy service.
- As a client, the access policy API can expect that the enterprise-subsidy service will answer
  redeemability queries with both a boolean answer *and* the current price of the content in question.

Open Questions and TODOs
========================

- We should formally declare "nothing about groups needs to be modeled at this time" for both the Subsidy API
  and its primary client, Subsidy Access Policy API.

Primary Subsidy Route
*********************
**/api/v1/subsidies/**
The root URL for reading simple metadata about enterprise subsidies.

GET (list) enterprise subsidies
===============================
**/api/v1/subsidies/?enterprise_customer_uuid=[customer-uuid]&subsidy_type={learner_credit,subscription}**

Inputs
------

- ``enterprise_customer_uuid`` (query param, optional): Specifies the enterprise for which associated subsidy metadata records should be returned.
- ``subsidy_type`` (query param, optional): Specifies what type of subsidy metadata records should be returned.  Allowed values are ``learner_credit`` and ``subscription``.

Outputs
-------
Returns a paginated list of subsidy metadata records of the form:

::

   {
       'count': 1,
       'next': null,
       'previous': null,
       'results': [
           {
               'uuid': 'the-subsidy-uuid',
               'enterprise_customer_uuid': 'the-enterprise-uuid',
               'active_datetime': '2023-01-01T00:00:00Z',
               'expiration_datetime': '2024-01-01T00:00:00Z',
               'title': 'The Learner Credit Subsidy for my Enterprise',
               'subsidy_type': 'learner_credit',
               'unit': 'USD_CENTS',
               'opportunity_id': 'some-opp-id',
               'remaining_balance': 987650
           }
       ]
   }

For some types of subsidies, e.g. subscriptions, this payload may also include things like `subscription_plan_uuid`.

Permissions
-----------

**enterprise_admin**
  Should only list subsidies for which the requesting user has implicit (JWT) or explicit (DB-defined) access.
  Optionally filtered to only the enterprises specified by the ``enterprise_customer_uuid`` query parameter.

**openedx_operator**
  If the requesting user is implicitly or explicitly granted this role, they have permissions to view **all**
  subsidy records.  Optionally filtered to only the enterprises specified by the ``enterprise_customer_uuid`` query parameter.


GET (retrieve) enterprise subsidy
=================================
**/api/v1/subsidies/[subsidy-uuid]/**

Inputs
------

- ``subsidy-uuid`` (URL path, required): The uuid (primary key) of the subsidy to retrieve.

Outputs
-------
Returns a single subsidy metadata records of the form:

::

   {
       'uuid': 'the-subsidy-uuid',
       'enterprise_customer_uuid': 'the-enterprise-uuid',
       'active_datetime': '2023-01-01T00:00:00Z',
       'expiration_datetime': '2024-01-01T00:00:00Z',
       'title': 'The Learner Credit Subsidy for my Enterprise',
       'subsidy_type': 'learner_credit',
       'unit': 'USD_CENTS',
       'opportunity_id': 'some-opp-id',
       'remaining_balance': 987650
   }

Permissions
-----------

enterprise_admin
  Should return the requested subsidy only if the requesting user has implicit (JWT) or explicit (DB-defined)
  ``enterprise_admin`` role assigned for the requested subsidy's enterprise.

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to view **all**
  subsidy records, and can therefore retrieve the requested subsidy.

Disallowed actions/verbs
========================
None of ``POST``, ``PATCH``, ``PUT``, or ``DELETE`` should be supported at this time.
Currently, subsidy records must be created by a staff user via Django Admin. We don't support the creation
of subsidies via a user-facing UI or from any other service.
Neither deletions or modifications to a subsidy (e.g. the `title` field) are supported via a user-facing UI at this time.
Any modifications that need to occur must be done by staff via Django Admin. Deletions of subsidies
should not be enabled via the API (though perhaps are possible via Django Admin).

Subsidy Transactions
********************
**/api/v1/subsidies/[subsidy-uuid]/transactions/**
The root URL for reading aggregate and transaction-level data about the transactions
associated with a subsidy.

GET (list) enterprise subsidy transactions
==========================================
**/api/v1/subsidies/[subsidy-uuid]/transactions/?include_aggregates={true,false}**

This endpoint can answer questions like:

- Tell me all of the transactions for a given subsidy.
- Within a subsidy, give me all transactions for a specific user or content key.
- Given a user id and content key, tell me if a successful/committed transaction exists, that is,
  has the user previously redeemed this subsidy for this content?

Inputs
------

- ``subsidy-uuid`` (URL path, required): The uuid (primary key) of the subsidy for which transactions should be listed.
- ``include_aggregates`` (query param, optional): Specifies if aggregates (quantities, number of transactions) should be
  returned as part of the paginated response.  Defaults to ``true``.
- ``learner_id`` (query param, optional): If present, filters returned transactions and/or aggregates to only
  those associated with the specified ``learner_id`` value.
- ``content_key`` (query param, optional): If present, filters returned transactions and/or aggregates to only
  those associated with the specified ``content_key`` value.

Outputs
-------
Returns a paginated list of aggregate and transaction data:

::

   {
       'previous': null,
       'next': '...',
       'count': 'blah',
       'aggregates': {
           'total_quantity': 12350,
           'unit': 'USD_CENTS',
           'remaining_balance': 987650
       },
       'results': [
           {
               'uuid': 'the-transaction-uuid',
               'status': 'completed',  TODO: enumerate valid statuses
               'idempotency_key': 'the-idempotency-key',
               'learner_id': 54321,
               'content_key': 'demox_1234+2T2023',
               'quantity': 19900,
               'unit': 'USD_CENTS',
               'reference_id': 1234,
               'reference_table': 'enrollments',
               'subsidy_access_policy_uuid': 'a-policy-uuid',
               'metadata': {...},
               'created': 'created-datetime',
               'modified': 'modified-datetime',
               'reversals': []
           }
       ]
   }

Permissions
-----------

enterprise_learner
  The transaction data returned should be filtered to only those related to the requesting user, within
  the subsidy specified in the request's URL path.

enterprise_admin
  Should return the requested subsidy transactions only if the requesting user has implicit (JWT) or explicit (DB-defined)
  ``enterprise_admin`` role assigned for the requested subsidy's enterprise.

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to view **all**
  subsidy records, and can therefore retrieve the requested subsidy transactions.

GET (retrieve) enterprise subsidy transaction
=============================================
**/api/v1/transactions/[transaction-uuid]/**

This endpoint can retrieve a single transaction, provided the caller has the subsidy and transaction uuid.

Inputs
------

- ``subsidy-uuid`` (URL path, required): The uuid (primary key) of the subsidy for which a transaction should be retrieved.
- ``transaction-uuid`` (URL path, required): The uuid (primary key) of the transaction to retrieve.

Outputs
-------
Returns a single transaction object (or 404 if no such transaction exists).

::

   {
       'uuid': 'the-transaction-uuid',
       'status': 'completed',  TODO: enumerate valid statuses
       'idempotency_key': 'the-idempotency-key',
       'learner_id': 54321,
       'content_key': 'demox_1234+2T2023',
       'quantity': 19900,
       'unit': 'USD_CENTS',
       'reference_id': 1234,
       'reference_table': 'enrollments',
       'subsidy_access_policy_uuid': 'a-policy-uuid',
       'metadata': {...},
       'created': 'created-datetime',
       'modified': 'modified-datetime',
       'reversals': []
   }

Permissions
-----------

enterprise_learner
  The transaction object should only be returned if requesting user's ``lms_user_id`` matches the ``learner_id``
  for the transaction record.

enterprise_admin
  Should return the requested subsidy transaction only if the requesting user has implicit (JWT) or explicit (DB-defined)
  ``enterprise_admin`` role assigned for the requested subsidy's enterprise.

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to view **all**
  subsidy records, and can therefore retrieve the requested subsidy transaction.

POST enterprise subsidy transaction
===================================
**/api/v1/transactions/**

Create a new subsidy transaction in the subsidy's ledger.
Only service users (those with ``openedx_operator`` role assignment) can do this.
A side-effect of a successful POST request here is the creation of a course enrollment or entitlement
that "fulfills" the ledger transaction.
The subsidy-service should determine the price of the content before creating the transaction, relying
on the course-discovery service for this data.

Inputs
------

- ``subsidy_uuid`` (POST data, required): The uuid (primary key) of the subsidy for which transactions should be created.
- ``learner_id`` (POST data, required): The user for whom the transaction is written and for which a fulfillment should occur.
- ``content_key`` (POST data, required): The content for which a fulfillment is created.
- ``subsidy_access_policy_uuid`` (POST data, required):
      The uuid of the policy that allowed the ledger transaction to be created.

Outputs
-------
Returns data about the transaction.

.. code-block:: json

   {
       "uuid": "the-transaction-uuid",
       "state": "committed",
       "idempotency_key": "the-idempotency-key",
       "learner_id": 54321,
       "content_key": "demox_1234+2T2023",
       "quantity": 19900,
       "unit": "USD_CENTS",
       "reference_id": 1234,
       "reference_type": "PlaceholderOCMEnrollmentReferenceType",
       "subsidy_access_policy_uuid": "a-policy-uuid",
       "metadata": {...},
       "created": "created-datetime",
       "modified": "modified-datetime",
       "reversals": []
   }

Permissions
-----------

enterprise_learner
  NOT ALLOWED

enterprise_admin
  NOT ALLOWED

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to create
  transactions for any active ledgered-subsidy.

POST enterprise subsidy transaction reversal
============================================
**/api/v1/transactions/[transaction-uuid]/reverse**

Reverse a subsidy transaction in the subsidy's ledger.
Only service users (those with ``openedx_operator`` role assignment) can do this.
A possible side-effect of a successful POST request here is the downgrading of any associated ``verified``
enrollment records to the ``audit`` mode.
The subsidy-service should determine the price of the content before processing the reversal.

Inputs
------

- ``subsidy-uuid`` (URL path, required): The uuid (primary key) of the subsidy for which a transaction should be reversed.
- ``transaction-uuid`` (URL path, required): The uuid (primary key) of the transaction to reverse.

Outputs
-------
Returns data about the transaction and its reversals.

::

   {
       'uuid': 'the-transaction-uuid',
       'status': 'completed',
       'idempotency_key': 'the-idempotency-key',
       'learner_id': 54321,
       'content_key': 'demox_1234+2T2023',
       'quantity': 19900,
       'unit': 'USD_CENTS',
       'reference_id': 1234,
       'reference_table': 'enrollments',
       'subsidy_access_policy_uuid': 'a-policy-uuid',
       'metadata': {...},
       'created': 'created-datetime',
       'modified': 'modified-datetime',
       'reversals': [{
           'idempotency_key': 'the-reversal-idempotency-key',
           'created': 'created-datetime',
           'modified': 'modified-datetime',
           'quantity': -19900,
           'metadata': null,
       }]
   }

Permissions
-----------

enterprise_learner
  NOT ALLOWED

enterprise_admin
  NOT ALLOWED

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to reverse
  transactions for any active ledgered-subsidy.

GET can redeem in subsidy
==========================
**/api/v1/subsidies/[subsidy-uuid]/can_redeem/**

Answers the query "can the given user redeem for the given price or content?"
This is probably implemented as a DRF action route:
https://www.django-rest-framework.org/api-guide/viewsets/#marking-extra-actions-for-routing
Note that this endpoint will determine the price of the given content key from the course-discovery service.
The caller of this endpoint need not provide a price.

Inputs
------

- ``subsidy-uuid`` (URL path, required): The uuid (primary key) of the subsidy for which transactions should be listed.
- ``learner_id`` (POST data, required): The user to whom the query pertains.
- ``content_key`` (POST data, required): The content to which the query pertains.

Outputs
-------
Returns an object with the following structure:

::

   {
       'can_redeem': true (or false),
       'quantity': 19900,
       'unit': 'USD_CENTS',
   }

Permissions
-----------

enterprise_learner
  Allowed as long as the requesting user has this role assignment for the referenced subsidy's enterprise.

enterprise_admin
  Allowed as long as the requesting user has this role assignment for the referenced subsidy's enterprise.

openedx_operator
  Allowed as long as the requesting user has this role assignment for the referenced subsidy's enterprise.

Consequences
************

- Subsidies can only be created, modified, or deleted via Django Admin by staff users with appropriate permissions.
- Subsidy data can be **read only** by learners or admins.
- Subsidy transactions and reversals should only be created if the requesting user is an ``openedx_operator`` - a role
  typically reserved for internal staff or backend services.
- Subsidies and transactions only relate to a content `catalog` via a reference to the `subsidy access policy`
  which caused a transaction to be created.  We assume that whatever (user, content key) combination is contained
  in the payload to the ``POST /api/v1/subsidies/.../transactions/`` endpoint has already been verified for inclusion
  in an appropriate catalog.  This is unconcerning at present, as we will only allow service-users or openedx operators
  to create transactions.
- We won't track multiple access policies that might have allowed a subsidy/ledger transaction to be created.  If mulitple
  policies could have allowed this, it's up to the access policy API to decide which policy id to send in the transaction
  creation request.
- We'll start with very simple caching of content pricing (and any other needed metadata from course-discovery), without
  providing any levers for invalidation of that cached data.  This is acceptable as long as we start with a very small
  cache timeout (5 minutes as described above).  It's up to future implementors to do cache invalidation on, for example,
  an event-bus event from course-discovery which signals a change to the source of truth data.
- The only unit of measure for the MVP scope is ``USD_CENTS``.
- To allow for greater flexibility, we won't nest the ``transactions`` resource under the ``subsidies`` resource -
  transaction uuids are already globally unique and don't require knowing the subsidy id to access them.

Rejected Alternatives
*********************

- None.  We've committed to creating the ``enterprise-subsidy`` service and must provide an API for it.
