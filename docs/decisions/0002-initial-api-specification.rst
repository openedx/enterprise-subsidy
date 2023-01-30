0001 Purpose of This Repo
#########################

Status
******

**Draft**

.. TODO: When ready, update the status from Draft to Provisional or Accepted.

.. Standard statuses
    - **Draft** if the decision is newly proposed and in active discussion
    - **Provisional** if the decision is still preliminary and in experimental phase
    - **Accepted** *(date)* once it is agreed upon
    - **Superseded** *(date)* with a reference to its replacement if a later ADR changes or reverses the decision


Context
*******

This doc describes the API specification for the ``enterprise-subsidy`` service.  Consider each chapter below a "decision".


Root Subsidy Route
******************
**/api/v1/subsidies/**

GET (list) enterprise subsidies
===============================

Inputs
------

- ``enterprise_uuid`` (query param, optional): Specifies the enterprise for which associated subsidy metadata records should be returned.
- ``subsidy_type`` (query param, optional): Specifies what type of subsidy metadata records should be returned.  Allowed values are ``learner_credit`` and ``subscription``.

Outputs
-------
Returns a paginated list of subsidy metadata records of the form:

::

   {
       'uuid': 'the-subsidy-uuid',
       'customer_uuid': 'the-enterprise-uuid',
       'active_datetime': '2023-01-01T00:00:00Z',
       'expiration_datetime': '2024-01-01T00:00:00Z',
       'title': 'The Learner Credit Subsidy for my Enterprise',
       'subsidy_type': 'learner_credit',
       'unit': 'USD_CENTS',
       'opportunity_id': 'some-opp-id',
   }

Permissions
-----------

enterprise_admin
  Should only list subsidies for which the requesting user has implicit (JWT) or explicit (DB-defined) access.
  Optionally filtered to only the enterprises specified by the ``enterprise_uuid`` query parameter.

openedx_operator
  If the requesting user is implicitly or explicitly granted this role, they have permissions to view **all**
  subsidy records.  Optionally filtered to only the enterprises specified by the ``enterprise_uuid`` query parameter.


Consequences
************

TODO: Add what other things will change as a result of creating this repo.

.. This section describes the resulting context, after applying the decision. All consequences should be listed here, not just the "positive" ones. A particular decision may have positive, negative, and neutral consequences, but all of them affect the team and project in the future.

Rejected Alternatives
*********************

TODO: If applicable, list viable alternatives to creating this new repo and give reasons for why they were rejected. If not applicable, remove section.

.. This section lists alternate options considered, described briefly, with pros and cons.

References
**********

TODO: If applicable, add any references. If not applicable, remove section.

.. (Optional) List any additional references here that would be useful to the future reader. See `Documenting Architecture Decisions`_ and `OEP-19 on ADRs`_ for further input.

.. _Documenting Architecture Decisions: https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions
.. _OEP-19 on ADRs: https://open-edx-proposals.readthedocs.io/en/latest/best-practices/oep-0019-bp-developer-documentation.html#adrs
