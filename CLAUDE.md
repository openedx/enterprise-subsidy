# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Environment Setup

### Docker-based Development
This project uses Docker for local development. Key commands:

- `make dev.up.build-no-cache`: Initial setup - builds containers from scratch and starts services
- `make dev.up.build`: Regular development startup with build
- `make dev.up`: Start existing containers
- `make app-shell`: Enter the application container shell
- `./provision-enterprise-subsidy.sh`: Initial provisioning script (run after first build)

### Services and Ports
- Main application: http://localhost:18280/admin/
- MySQL 8.0 database (container: enterprise-subsidy.mysql80)
- Memcache for caching
- Event consumer service for learner credit course enrollment lifecycle events

### Event Bus (Kafka) Development
For working with openedx-events and Kafka:
- `make dev.up.with-events`: Start with local Kafka (includes Confluent Control Center at http://localhost:9021/clusters)
- Event consumption: `./manage.py consume_enterprise_ping_events`
- Event production: `./manage.py produce_enterprise_ping_event`

## Development Commands

### Requirements and Dependencies
- `make requirements`: Install/update dev requirements
- `make dev_requirements`: Sync to dev requirements
- `make validation_requirements`: Sync to requirements for testing & code quality

### Testing and Quality
- `make test`: Run tests with coverage (uses pytest)
- `make validate`: Run all tests, quality checks, PII checks, and keyword checks
- `pytest ./path/to/new/tests`: Run specific tests
- `make quality`: Run tox quality checks
- `make lint` / `make pylint`: Python linting with pylint
- `make style`: Python style checking with pycodestyle
- `make isort`: Sort imports, `make isort_check`: Check import sorting
- `make pii_check`: Check for PII annotations on Django models
- `make check_keywords`: Scan for restricted field names in Django models

### Database Operations
- `make migrate` / `make dev.migrate`: Apply database migrations
- `make db-shell-8`: MySQL 8 shell access
- `make dev.backup` / `make dev.restore`: Database backup/restore

### Static Files and Assets
- `make static` / `make dev.static`: Collect static files

## Architecture Overview

### Core Django Apps
- **subsidy**: Core subsidy models and business logic, including Subsidy model with ledger integration
- **transaction**: Transaction management, including ledger transactions and reversals
- **content_metadata**: Content metadata API integration and caching
- **fulfillment**: Handles fulfillment of subsidies, including GEAG (Get Enrolled & Get Assigned) fulfillment
- **api_client**: Client integrations with Enterprise API, Enterprise Catalog, and LMS User API
- **core**: Shared utilities, context processors, and base functionality

### Key Domain Concepts
- **Subsidies**: Store value (learner credit in USD or subscription seats) that can be redeemed for content
- **Ledger**: Tracks transactions (value movement in/out of subsidies) using openedx-ledger package
- **Redemption**: The act of redeeming stored value for content
- **Revenue Categories**: Control revenue recognition (bulk-enrollment-prepay, partner-no-rev-prepay)
- **Reference Types**: Links subsidies to originating objects (e.g., Salesforce OpportunityLineItem)

### External Service Integration
- **Enterprise Catalog Service**: Content metadata and pricing (http://localhost:18160)
- **LMS**: User data and enrollment operations
- **Event Bus**: openedx-events integration for cross-service communication
- **Course Discovery**: Source of truth for content pricing and metadata

### Data Models Architecture
- Subsidies use django-simple-history for change tracking
- Soft deletion pattern with `is_soft_deleted` field
- Integration with edx-rbac for role-based access control
- Uses openedx-ledger for transaction tracking and balance management

### API Design
- RESTful API with DRF (Django REST Framework)
- API versioning (v1, v2 endpoints)
- Integration with content metadata for price validation
- Redeemability queries return boolean + current content price

## Settings Configuration
- Base settings in `enterprise_subsidy/settings/base.py`
- Environment-specific configs: `devstack.py`, `local.py`, `production.py`, `test.py`
- Uses environment variables for service URLs and configuration