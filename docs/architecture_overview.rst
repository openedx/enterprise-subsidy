##########################
Architecture Overview
##########################

*************
Introduction
*************

Welcome to the enterprise-subsidy service architecture overview. This document provides a comprehensive guide for developers new to the edX ecosystem who need to understand how this service works, its role in the broader edX enterprise platform, and how to work with its codebase effectively.

**What is enterprise-subsidy?**

The enterprise-subsidy service is a Django-based microservice that manages financial subsidies for enterprise customers in the edX platform. It tracks and balances enterprise-funded learning transactions, allowing companies to provide learning credits to their employees that can be redeemed for courses, programs, and other educational content.

**Key Concepts for edX Newcomers**

Before diving into the architecture, here are essential edX ecosystem concepts:

- **Enterprise Customer**: A company that purchases learning solutions for their employees
- **Learner Credit**: Monetary value (in USD cents) that can be redeemed for educational content
- **Content**: Courses, programs, and other educational materials offered on the edX platform
- **Enrollment**: The act of registering a learner for specific educational content
- **Fulfillment**: The process of converting a subsidy redemption into an actual enrollment

****************************
System Context & Integration
****************************

edX Enterprise Ecosystem Overview
==================================

The enterprise-subsidy service operates within a microservices ecosystem. Here's how it fits into the broader edX enterprise platform:

.. code-block:: text

    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │   Salesforce    │    │  Enterprise     │    │   Enterprise    │
    │   (Source of    │    │   Admin         │    │   Learner portal│
    │   Truth for     │    │   Portal        │    │                 │
    │   Contracts)    │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘
              │                       │                       │
        (manual link)                 ▼-----------------------                      
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  Enterprise     │    │  Enterprise     │    │      LMS        │
    │   Subsidy       │◄──►│   Access        │◄──►│  (edxapp and    │
    │ (This Service)  │    │ (Policy Engine) │    │  edx-enterprise │
    │                 │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘
              │                       │                       │
              ▼                       ▼                       ▼
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  Enterprise     │    │  cron jobs      │    │ course-discovery|
    │   Catalog       │    │ and celery tasks│    │   (Content      │
    │ (Content        │◄──►│   (Kafka)       │◄──►│   Metadata)     │
    │  Metadata)      │    │                 │    │                 │
    └─────────────────┘    └─────────────────┘    └─────────────────┘

Key Service Interactions
=========================

1. **Enterprise Access Service**: Determines access policies and approval workflows
2. **Enterprise Catalog Service**: Provides content metadata and pricing information
3. **edxapp LMS (edx-enterprise)**: Handles actual course enrollments
4. **Discovery Service**: Source of truth for content pricing and metadata
5. **Event Bus (Kafka)**: Enables event-driven communication between services

**********************
Application Architecture
**********************

Django Application Structure
=============================

The service follows Django's app-based architecture with clear separation of concerns:

.. code-block:: text

    enterprise_subsidy/
    ├── apps/
    │   ├── api/              # REST API endpoints and serializers
    │   │   ├── v1/           # API version 1 (primary)
    │   │   └── v2/           # API version 2 (deposits)
    │   ├── api_client/       # External service integration
    │   ├── content_metadata/ # Content pricing and metadata caching
    │   ├── core/             # Shared utilities and base models
    │   ├── fulfillment/      # Enrollment fulfillment logic
    │   ├── subsidy/          # Core subsidy domain models
    │   └── transaction/      # Transaction management and ledger
    ├── settings/             # Environment-specific configurations
    └── static/               # Static assets

Core Domain Model Relationships
===============================

Here's how the main domain models relate to each other:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │                        Domain Models                            │
    │                                                                 │
    │  ┌─────────────────┐                ┌─────────────────┐        │
    │  │   Enterprise    │                │    Salesforce   │        │
    │  │    Customer     │                │  Opportunity    │        │
    │  │   (External)    │                │   Line Item     │        │
    │  │                 │                │  (External)     │        │
    │  └─────────────────┘                └─────────────────┘        │
    │           │                                   │                 │
    │           │ Referenced by                     │ Referenced by   │
    │           ▼                                   ▼                 │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │                     Subsidy                                 │ │
    │  │ ┌─────────────────────────────────────────────────────────┐ │ │
    │  │ │ • UUID (Primary Key)                                    │ │ │
    │  │ │ • Title (Human-readable identifier)                     │ │ │
    │  │ │ • Starting Balance (Initial funding amount)             │ │ │
    │  │ │ • Enterprise Customer UUID (Foreign reference)         │ │ │
    │  │ │ • Reference ID (Links to Salesforce Opportunity)       │ │ │
    │  │ │ • Unit (Currency: USD_CENTS)                            │ │ │
    │  │ │ • Revenue Category (Business classification)            │ │ │
    │  │ │ • Is Soft Deleted (Logical deletion flag)              │ │ │
    │  │ └─────────────────────────────────────────────────────────┘ │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    │                                │                                 │
    │                     One-to-One │                                 │
    │                                ▼                                 │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │                    Ledger                                   │ │
    │  │                 (openedx-ledger)                            │ │
    │  │ ┌─────────────────────────────────────────────────────────┐ │ │
    │  │ │ • Tracks all financial transactions                     │ │ │
    │  │ │ • Maintains running balance                             │ │ │
    │  │ │ • Provides transaction history                          │ │ │
    │  │ │ • Enforces business rules (no overdrafts, etc.)        │ │ │
    │  │ └─────────────────────────────────────────────────────────┘ │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    │                                │                                 │
    │                    One-to-Many │                                 │
    │                                ▼                                 │
    │  ┌─────────────────────────────────────────────────────────────┐ │
    │  │                 Transactions                                │ │
    │  │              (openedx-ledger)                               │ │
    │  │ ┌─────────────────────────────────────────────────────────┐ │ │
    │  │ │ • Individual debit/credit entries                       │ │ │
    │  │ │ • Content Key (What was purchased)                      │ │ │
    │  │ │ • Learner Email (Who made the purchase)                 │ │ │
    │  │ │ • Amount (How much was spent)                           │ │ │
    │  │ │ • State (Pending, Committed, Failed)                    │ │ │
    │  │ │ • Idempotency Key (Prevents duplicates)                 │ │ │
    │  │ │ • Fulfillment Identifier (Links to enrollment)          │ │ │
    │  │ └─────────────────────────────────────────────────────────┘ │ │
    │  └─────────────────────────────────────────────────────────────┘ │
    │                                                                 │
    └─────────────────────────────────────────────────────────────────┘

Data Flow Architecture
======================

Transaction Lifecycle
---------------------

Here's a simplified look at how learner credit redemption flows through the system:

.. code-block:: text

    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
    │   Learner   │    │  Frontend   │    │ Enterprise  │    │ Enterprise  │
    │             │    │ Application │    │   Access    │    │  Subsidy    │
    │             │    │             │    │ (Policy)    │    │             │
    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
           │                   │                   │                   │
           │ 1. Browse & Select│                   │                   │
           │    Course         │                   │                   │
           ├──────────────────►│                   │                   │
           │                   │ 2. Check Access   │                   │
           │                   │    Policy         │                   │
           │                   ├──────────────────►│                   │
           │                   │                   │ 3. Check          │
           │                   │                   │    Redeemability  │
           │                   │                   ├──────────────────►│
           │                   │                   │                   │
           │                   │                   │ 4. Price &        │
           │                   │                   │    Availability   │
           │                   │                   │◄──────────────────┤
           │                   │ 5. Access         │                   │
           │                   │    Approved       │                   │
           │                   │◄──────────────────┤                   │
           │ 6. Confirm        │                   │                   │
           │    Enrollment     │                   │                   │
           │◄──────────────────┤                   │                   │
           │                   │                   │                   │
           │ 7. Enroll Request │                   │                   │
           ├──────────────────►│                   │                   │
           │                   │ 8. Create         │                   │
           │                   │    Transaction    │                   │
           │                   ├─────────────────────────────────────► │
           │                   │                   │                   │
           │                   │                   │ ┌─────────────────┴─
           │                   │                   │ │ 9. Process:        │
           │                   │                   │ │ • Validate Price   │
           │                   │                   │ │ • Create Ledger    │
           │                   │                   │ │   Transaction      │
           │                   │                   │ │ • Fulfill Enrollment
           │                   │                   │ │ • Emit Events      
           │                   │                   │ └─────────────────┬─-
           │                   │                   │                   │
           │                   │ 10. Transaction   │                   │
           │                   │     Success       │                   │
           │                   │◄───────────────────────────────────── ┤
           │ 11. Enrollment    │                   │                   │
           │     Confirmation  │                   │                   │
           │◄──────────────────┤                   │                   │

API Architecture
================

REST API Design with Django REST Framework
-------------------------------------------

The service implements a comprehensive REST API using Django REST Framework (DRF) patterns and best practices:

.. code-block:: text

    API Layer Architecture:
    
    ┌─────────────────────────────────────────────────────────────────┐
    │                     HTTP Request Layer                          │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │  Authentication │  │   Permissions   │  │    Throttling   │ │
    │  │ • JWT (Service) │  │ • RBAC-based    │  │ • Rate Limiting │ │
    │  │ • Session (Web) │  │ • Role Required │  │                 │ │
    │  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                        ViewSet Layer                            │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │  SubsidyViewSet │  │TransactionViewSet│  │ContentMetadata  │ │
    │  │                 │  │                 │  │    ViewSet      │ │
    │  │ • CRUD + Custom │  │ • CRUD + Reverse│  │ • Read Only     │ │
    │  │ • can_redeem()  │  │ • Filters       │  │ • Price Check   │ │
    │  │ • aggregates    │  │ • Pagination    │  │                 │ │
    │  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                      Serializer Layer                           │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │     Request     │  │    Response     │  │   Validation    │ │
    │  │  Serializers    │  │  Serializers    │  │   Serializers   │ │
    │  │                 │  │                 │  │                 │ │
    │  │ • Input Parsing │  │ • Output Format │  │ • Business      │ │
    │  │ • Field Mapping │  │ • Computed      │  │   Rules         │ │
    │  │                 │  │   Fields        │  │ • Data Types    │ │
    │  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    Business Logic Layer                         │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
    │  │   Service APIs  │  │   Domain Models │  │  External APIs  │ │
    │  │ • subsidy.api   │  │ • Subsidy Model │  │ • api_client.*  │ │
    │  │ • transaction   │  │ • Ledger (ext.) │  │ • Fulfillment   │ │
    │  │ • fulfillment   │  │ • User Model    │  │                 │ │
    │  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
    └─────────────────────────────────────────────────────────────────┘

ViewSet Patterns
----------------

**1. ModelViewSet Pattern (SubsidyViewSet)**

- Inherits from ``GenericViewSet`` with selective mixins
- Uses ``PermissionRequiredForListingMixin`` for RBAC integration
- Custom actions via ``@action`` decorator for business operations
- Lookup by UUID instead of primary key

**2. Custom Action Pattern**

.. code-block:: python

    @action(detail=True, methods=['get'])
    def can_redeem(self, request, uuid=None):
        # Custom business logic endpoint
        # Returns pricing and availability information

**3. Filter Integration**

- Uses ``django-filter`` with custom ``HelpfulFilterSet``
- Integrates filter help text with API documentation
- Supports complex filtering (MultipleChoiceFilter for transaction states)

Serializer Architecture
-----------------------

**1. Separation of Concerns**

- **Request Serializers**: Handle input validation and parsing (``*RequestSerializer``)
- **Response Serializers**: Format output with computed fields (``SubsidySerializer``)
- **Domain Serializers**: Map directly to model fields (``TransactionSerializer``)

**2. Computed Fields Pattern**

.. code-block:: python

    current_balance = serializers.SerializerMethodField()
    
    @extend_schema_field(serializers.IntegerField)
    def get_current_balance(self, obj) -> int:
        return obj.current_balance()

**3. API Documentation Integration**

- Uses ``drf-spectacular`` for OpenAPI schema generation
- Field-level help text automatically included in docs
- Custom schema extensions via ``@extend_schema_field``

Pagination Strategy
-------------------

**Custom Pagination Classes**

1. **SubsidyListPaginator**: Adds computed page count for frontend pagination controls
2. **TransactionListPaginator**: Includes aggregate data (total quantities, remaining balances) in paginated responses

**Conditional Aggregates**

.. code-block:: python

    if request.query_params.get("include_aggregates"):
        # Add business-specific aggregate data to response
        aggregates = {
            "remaining_subsidy_balance": subsidy.current_balance(),
            "total_quantity": ledger.subset_balance(queryset)
        }

URL and Routing Patterns
------------------------

**Version-based URL Structure**

.. code-block:: text

    /api/v1/
    ├── subsidies/                    # DRF Router-based
    │   ├── {uuid}/
    │   ├── {uuid}/can_redeem/        # Custom action
    │   └── {uuid}/transactions/      # Nested resource
    ├── transactions/                 # DRF Router-based
    │   ├── {uuid}/
    │   └── {uuid}/reverse/           # Custom action
    └── content-metadata/{id}/        # Individual view

**Routing Configuration**

- Uses DRF's ``DefaultRouter`` for standard CRUD operations
- Manual URL patterns for custom endpoints and nested resources
- Consistent UUID-based lookups across all resources

Error Handling Patterns
------------------------

**Standardized Error Responses**

.. code-block:: python

    response.data = {
        "error_code": "subsidy_not_found",
        "developer_message": "Technical details",
        "user_message": "User-friendly message"
    }

**Exception Handling Hierarchy**

1. **Business Logic Exceptions**: Custom domain exceptions (``PriceValidationError``)
2. **DRF Built-in Exceptions**: Authentication, permissions, validation
3. **External Service Exceptions**: API client failures, timeouts
4. **Server Errors**: Catch-all with correlation IDs for debugging

Authentication & Authorization Integration
------------------------------------------

**Multi-layered Security**

1. **Authentication Classes**: JWT for service-to-service, Session for web
2. **Permission Classes**: Combined with RBAC for fine-grained control
3. **Role-based Filtering**: Automatic query filtering based on user roles
4. **Enterprise Context**: All operations scoped to enterprise customer

**RBAC Integration Pattern**

.. code-block:: python

    class SubsidyViewSet(PermissionRequiredForListingMixin, ...):
        allowed_roles = [ENTERPRISE_SUBSIDY_ADMIN_ROLE, ...]
        role_assignment_class = EnterpriseSubsidyRoleAssignment
        list_lookup_field = "enterprise_customer_uuid"

This architecture provides a robust, scalable REST API that follows DRF best practices while implementing enterprise-specific business requirements and security patterns.


External Service Integration
============================

API Client Architecture
-----------------------

The service integrates with multiple external services through dedicated API clients:

.. code-block:: text

    ┌─────────────────────────────────────────────────────────────────┐
    │                    API Client Layer                             │
    │                                                                 │
    │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
    │  │  Enterprise     │  │  Enterprise     │  │    LMS User     │  │
    │  │  API Client     │  │  Catalog        │  │   API Client    │  │
    │  │                 │  │  API Client     │  │                 │  │
    │  │ • Customer Data │  │ • Content       │  │ • User Profile  │  │
    │  │ • Enrollments   │  │   Metadata      │  │ • Authentication│  │
    │  │ • Fulfillment   │  │ • Pricing       │  │                 │  │
    │  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
    │           │                     │                     │         │
    │           ▼                     ▼                     ▼         │
    │  ┌─────────────────────────────────────────────────────────────┐│
    │  │              Base OAuth Client                              ││
    │  │ • Token Management                                          ││
    │  │ • Request Authentication                                    ││
    │  │ • Error Handling & Retries                                  ││
    │  │ • Response Caching (5-minute TTL for content pricing)       ││
    │  └─────────────────────────────────────────────────────────────┘│
    └─────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                   External Services                             │
    └─────────────────────────────────────────────────────────────────┘

Event-Driven Architecture
=========================

The service participates in an event-driven ecosystem using Kafka:

.. code-block:: text

    Event Flow:
    
    ┌─────────────────┐                    ┌─────────────────┐
    │  Enterprise     │   Enrollment       │     Event       │
    │   Subsidy       │   Lifecycle        │      Bus        │
    │  (Producer &    │    Events          │   (Kafka)       │
    │   Consumer)     │◄──────────────────►│                 │
    └─────────────────┘                    └─────────────────┘
              │                                       │
              │ Produces:                             │ Consumes:
              │ • Transaction Events                  │ • Enrollment Updates
              │ • Subsidy Balance Updates             │ • Unenrollment Events
              │ • Enrollment Fulfillment              │ • Content Updates
              │                                       │
              ▼                                       ▼
    ┌─────────────────┐                    ┌─────────────────┐
    │   Downstream    │                    │   Upstream      │
    │   Services      │                    │   Services      │
    │                 │                    │                 │
    │ • Enterprise    │                    │ • LMS           │
    │   Access        │                    │ • Enterprise    │
    │                 │                    │   Catalog       │
    │                 │                    │                 │
    └─────────────────┘                    └─────────────────┘

*********************************
Development Workflow & Patterns
*********************************

Code Organization Patterns
===========================

The codebase follows several key patterns that developers should understand:

**1. Django App Separation by Domain**

Each Django app represents a clear business domain:

- ``subsidy/``: Core business logic for subsidy management
- ``transaction/``: Financial transaction handling and ledger integration
- ``fulfillment/``: Enrollment fulfillment and course assignment
- ``content_metadata/``: Content pricing and metadata caching
- ``api_client/``: External service integration layer

**2. API Versioning Strategy**

- ``/api/v1/``: Stable, production API
- ``/api/v2/``: New features (deposits) with potential breaking changes
- Backward compatibility maintained within major versions

**3. Service Layer Pattern**

Business logic is encapsulated in service classes rather than being scattered across views and models:

- API classes in each app handle business operations
- Models focus on data representation and simple validations
- Views handle HTTP concerns and delegate to service layer

**4. External Integration Pattern**

All external service calls go through dedicated API client classes:

- Centralized authentication and error handling
- Consistent retry and timeout policies
- Response caching where appropriate (content pricing)

Common Development Tasks
========================

**Adding New API Endpoints**

1. Define serializers in ``apps/api/v{X}/serializers.py``
2. Create view classes in ``apps/api/v{X}/views/``
3. Add URL patterns in ``apps/api/v{X}/urls.py``
4. Add business logic to appropriate app's ``api.py`` module
5. Write comprehensive tests in ``apps/api/v{X}/tests/``

**Working with Subsidies**

1. All subsidy operations should go through the ``Subsidy`` model methods
2. Use the ``ActiveSubsidyManager`` to exclude soft-deleted subsidies
3. Leverage the openedx-ledger integration for transaction management
4. Always validate content pricing through ``ContentMetadataApi``

**Event Integration**

1. Event production happens in ``apps/core/event_bus.py``
2. Event consumption is handled by dedicated management commands
3. Use idempotency keys to prevent duplicate processing
4. Test event flows with the local Kafka setup

**********************
Security & Compliance
**********************

Authentication & Authorization
==============================

The service uses a multi-layered security approach:

**1. OAuth2 Integration**

- Integrates with edX's OAuth2 provider (LMS)
- Service-to-service authentication for API clients
- Token-based authentication for user-facing endpoints

**2. Role-Based Access Control (RBAC)**

Uses ``edx-rbac`` for fine-grained permissions:

.. code-block:: text

    Role Hierarchy:
    
    System Roles (Cross-Enterprise):
    ├── SYSTEM_ENTERPRISE_ADMIN_ROLE
    ├── SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE
    ├── SYSTEM_ENTERPRISE_LEARNER_ROLE
    └── SYSTEM_ENTERPRISE_OPERATOR_ROLE
    
    Enterprise-Specific Roles:
    ├── ENTERPRISE_SUBSIDY_ADMIN_ROLE
    ├── ENTERPRISE_SUBSIDY_LEARNER_ROLE
    └── ENTERPRISE_SUBSIDY_OPERATOR_ROLE

**3. Data Privacy & PII Handling**

- PII annotations on models for compliance tracking
- Data retention policies enforced through soft deletion
- Audit trails maintained through django-simple-history
