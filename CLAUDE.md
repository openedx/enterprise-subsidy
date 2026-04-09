# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Enterprise Subsidy is a Django-based microservice within the Open edX ecosystem that manages financial subsidies for enterprise customers. It captures and balances enterprise-subsidized transactions, tracking learner credit (monetary value in USD cents) that can be redeemed for educational content.

## Test and Quality Instructions

- To run unit tests or generate coverage reports, invoke the `unit-tests` skill.
- To run quality checks (linting, style), invoke the `quality-tests` skill.

## Code Navigation

- Prefer using the LSP tool over grep/glob when navigating Python code (definitions, references, type info)

## Key Principles

- Search the codebase before assuming something isn't implemented
- Write comprehensive tests with clear documentation
- Follow Test-Driven Development when refactoring or modifying existing functionality
- Always write tests for new functionality you implement
- Make a note of when tests for some functionality have been completed. If you cannot run the tests, ask me to run them manually, then confirm whether they succeeded or failed.
- Keep changes focused and minimal
- Follow existing code patterns
- Prefer the `ddt` package for parameterized tests to reduce code duplication

## Documentation & Institutional Memory

- Document new functionality in `docs/decisions/` for architectural decisions or `docs/how_to/` for operational guides
- When you learn something important about how this codebase works (gotchas, non-obvious patterns, integration quirks), capture it in the relevant documentation or suggest creating a new doc file
- These docs are institutional memory - future sessions (yours or others) will benefit from what you record here

## Architecture Overview

This is a Django service for managing enterprise subsidies and tracking subsidized transactions. The `docs/architecture_overview.rst` provides comprehensive documentation on the service architecture, domain models, and data flows.

### Core Applications

- **api** - REST API endpoints with DRF, including v1 and v2 versioned views
- **subsidy** - Core subsidy domain models and business logic, including Subsidy model with ledger integration
- **transaction** - Transaction management and ledger operations for tracking credit usage
- **content_metadata** - Content metadata API integration, caching, and price validation
- **fulfillment** - Handles fulfillment of subsidies (converting redemptions into actual enrollments)
- **api_client** - External service integrations (Enterprise API, Enterprise Catalog, LMS User API)
- **core** - Shared utilities, context processors, and base functionality

### Key Concepts

- **Subsidy**: Store of value (learner credit in USD cents or subscription seats) that can be redeemed for content
- **Ledger**: Tracks all financial transactions (debits/credits) using the openedx-ledger package
- **Transaction**: Individual debit/credit entry representing value movement
- **Redemption**: The act of redeeming stored value from a subsidy for educational content
- **Fulfillment**: The process of converting a redemption into an actual enrollment
- **Revenue Categories**: Business classifications controlling revenue recognition (bulk-enrollment-prepay, partner-no-rev-prepay)
- **Reference Types**: Links subsidies to originating objects (e.g., Salesforce OpportunityLineItem)

### External Service Integration

- **Enterprise Catalog**: Content metadata and pricing information (http://localhost:18160)
- **Enterprise Access**: Determines access policies and approval workflows
- **LMS (edxapp)**: User management and course enrollment operations
- **Discovery Service**: Source of truth for content pricing and metadata
- **Event Bus (Kafka)**: Enables event-driven communication between services

### Local Development

- This service may be included in the [edx/devstack](https://github.com/openedx/devstack) repository for integration testing alongside the rest of the Open edX ecosystem
- Server runs on `localhost:18280`
- Uses Docker with MySQL 8.0, Memcache for caching
- Event consumer service for learner credit course enrollment lifecycle events
- Kafka event bus available via `make dev.up.with-events` (Confluent Control Center at http://localhost:9021/clusters)

### Key Design Patterns

- Uses django-simple-history for change tracking on subsidy models
- Soft deletion pattern with `is_soft_deleted` field
- Integration with edx-rbac for role-based access control
- Ledger-based transaction tracking with openedx-ledger package
- Versioned cache keys for key-based cache invalidation
- TieredCache combining RequestCache with memcached

## Testing Notes

- Uses pytest with Django integration
- Coverage reporting enabled by default
- PII annotation checks required for Django models (via `make pii_check`)
- Restricted keyword checks for Django model fields (via `make check_keywords`)
