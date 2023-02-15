0004 Cross-service data linking
###############################

Status
******

**Accepted** February 2023

Context
*******

The enterprise-subsidy service is a central piece in the redemption and fulfillment flow
that results in the creation of enterprise enrollments via Subsidy value. Notably, there are
bi-directional references between the ``subsidy access policy`` app of the ``enterprise-access`` service,
and the enrollments interface of ``edx-enterprise``.  These two-way references help ensure
the veracity of our business records and provide a path for robust reporting on the history
of a given subsidized enterprise course enrollment.

Decision
********

There are several model fields in the ``enterprise-subsidy`` service, and its main plugin,
the ``openedx-ledger`` library that achieve the desired bi-directional reference property.

This `entity-relationship diagram`_ demonstrates the references.


References with enterprise-access
=================================

The ``SubsidyAccessPolicy`` model's table contains a reference to the ``uuid`` of ``LearnerCreditSubsidy``
(or any other implementation of the abstract ``Subsidy`` model).  This is necessary for the policy to
know which subsidy record should have the transaction for a given redemption action.

In ``enterprise-subsidy``, the Ledger ``Transaction`` table will contain a ``subsidy_access_policy`` field
that refers to the access policy record that allowed a given transaction to be created.

References with edx-enterprise
==============================

In ``edx-enterprise``, the ``LearnerCreditEnterpriseCourseEnrollment`` table contains a ``transaction_uuid`` field
that refers to the ledger ``transaction`` that is fulfilled by a certain enrollment.  This same table
also contains references to any ``EnterpriseCourseEntitlement`` or ``EnterpriseCourseEnrollment`` records
that are created as part of that fulfillment.

The ledger ``Transaction`` table contains a ``reference_id`` field that refers to the ``uuid`` (primary key)
of the edx-enterprise ``LearnerCreditEnterpriseCourseEnrollment`` table.  This allows the transaction to "commit" -
that is, it allows us to know that the fulfillment process related to the transaction's creation has
completed successfully.

Note that an analagous ``LicensedEnterpriseCourseEnrollment`` model also exists in edx-enterprise, and serves a similar
purpose for cross-linking to the ``license-manager`` service.

Consequences
************

- The ``uuid`` of a ``Subsidy`` record must somehow make its way into the relevant ``SubsidyAccessPolicy`` record.
- Downstream stakeholders must be aware of the existance and purpose of these fields to do any required
  reporting coherently.
- Puts us at some small risk of introducing coupling between the data of different services.

Rejected Alternatives
*********************

No serious alternatives considered - these sorts of bi-directional references became somewhat necessary
when we adopted a design that encapsulates the bounded context of `Enterprise subsidies` as a discrete
microservice.

.. _entity-relationship diagram: https://github.com/openedx/enterprise-subsidy/blob/main/docs/decisions/0004-cross-service-data-linking.png
