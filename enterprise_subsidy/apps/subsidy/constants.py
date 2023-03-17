"""
Constants for the subsidy app.
"""

# System-wide roles defined by edx-enterprise, used across the entire openedx instance, and can be found in JWT tokens.
SYSTEM_ENTERPRISE_LEARNER_ROLE = 'enterprise_learner'
SYSTEM_ENTERPRISE_ADMIN_ROLE = 'enterprise_admin'
SYSTEM_ENTERPRISE_OPERATOR_ROLE = 'enterprise_openedx_operator'
SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE = 'enterprise_subsidy_admin'

# Feature roles specific to the subsidy service.  They are basically mapped 1:1 with the system-wide roles.
ENTERPRISE_SUBSIDY_LEARNER_ROLE = 'enterprise_learner'
ENTERPRISE_SUBSIDY_ADMIN_ROLE = 'enterprise_subsidy_admin'
ENTERPRISE_SUBSIDY_OPERATOR_ROLE = 'enterprise_subsidy_operator'

# Permissions directly control the specific code paths and functionality granted to the user within the subsidy app.
PERMISSION_CAN_CREATE_TRANSACTIONS = "subsidy.can_create_transactions"
PERMISSION_CAN_READ_SUBSIDIES = "subsidy.can_read_subsidies"
PERMISSION_CAN_READ_TRANSACTIONS = "subsidy.can_read_transactions"
PERMISSION_CAN_READ_CONTENT_METADATA = "subsidy.can_read_metadata"
# Provide a convenience permission which should never be granted.  This is helpful for being explicit when overriding
# `get_permission_required()`.
PERMISSION_NOT_GRANTED = 'subsidy.not_granted'

EXECUTIVE_EDUCATION_MODE = "paid-executive-education"
EDX_PRODUCT_SOURCE = "edX"
EDX_VERIFIED_COURSE_MODE = "verified"
