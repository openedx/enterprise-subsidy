import os
from os.path import abspath, dirname, join

from corsheaders.defaults import default_headers as corsheaders_default_headers

from enterprise_subsidy.apps.subsidy.constants import (
    ENTERPRISE_SUBSIDY_ADMIN_ROLE,
    ENTERPRISE_SUBSIDY_LEARNER_ROLE,
    ENTERPRISE_SUBSIDY_OPERATOR_ROLE,
    SYSTEM_ENTERPRISE_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE,
    SYSTEM_ENTERPRISE_LEARNER_ROLE,
    SYSTEM_ENTERPRISE_OPERATOR_ROLE
)
from enterprise_subsidy.settings.utils import get_logger_config

# PATH vars
PROJECT_ROOT = join(abspath(dirname(__file__)), "..")


def root(*path_fragments):
    return join(abspath(PROJECT_ROOT), *path_fragments)


LMS_URL = os.environ.get('LMS_URL', 'localhost:18000')
ENTERPRISE_CATALOG_URL = os.environ.get('ENTERPRISE_CATALOG_URL', 'https://localhost:18160')
ENTERPRISE_SUBSIDY_URL = os.environ.get('ENTERPRISE_SUBSIDY_URL', 'https://localhost:18280')
FRONTEND_APP_LEARNING_URL = os.environ.get('FRONTEND_APP_LEARNING_URL', 'https://localhost:2000')

BULK_ENROLL_REQUEST_TIMEOUT_SECONDS = os.environ.get('BULK_ENROLL_REQUEST_TIMEOUT_SECONDS', 20)

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('EDX_ENTERPRISE_SUBSIDY_SECRET_KEY', 'insecure-secret-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = (
    'clearcache',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
)

THIRD_PARTY_APPS = (
    'corsheaders',
    'csrf.apps.CsrfAppConfig',  # Enables frontend apps to retrieve CSRF tokens
    'django_filters',
    'django_object_actions',
    'djangoql',
    'drf_spectacular',
    'drf_yasg',
    # "App Permissions" compatiblity: this provides the manage_user and manage_group management commands.
    'edx_django_utils.user',
    'openedx_ledger',
    'release_util',
    'rest_framework',
    'simple_history',
    'social_django',
    'waffle',
    'rules.apps.AutodiscoverRulesConfig',
    'openedx_events',
)

PROJECT_APPS = (
    'enterprise_subsidy.apps.core',
    'enterprise_subsidy.apps.api',
    'enterprise_subsidy.apps.subsidy',
    'enterprise_subsidy.apps.fulfillment',
    'enterprise_subsidy.apps.content_metadata',
    'enterprise_subsidy.apps.transaction'
)

INSTALLED_APPS += THIRD_PARTY_APPS
INSTALLED_APPS += PROJECT_APPS

MIDDLEWARE = (
    'log_request_id.middleware.RequestIDMiddleware',

    # Resets RequestCache utility for added safety.
    'edx_django_utils.cache.middleware.RequestCacheMiddleware',

    # Monitoring middleware should be immediately after RequestCacheMiddleware
    'edx_django_utils.monitoring.DeploymentMonitoringMiddleware',  # python and django version
    'edx_django_utils.monitoring.CookieMonitoringMiddleware',  # cookie names (compliance) and sizes
    'edx_django_utils.monitoring.CachedCustomMonitoringMiddleware',  # support accumulate & increment
    'edx_django_utils.monitoring.MonitoringMemoryMiddleware',  # memory usage

    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'edx_rest_framework_extensions.auth.jwt.middleware.JwtAuthCookieMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'social_django.middleware.SocialAuthExceptionMiddleware',
    'waffle.middleware.WaffleMiddleware',
    # Enables force_django_cache_miss functionality for TieredCache.
    'edx_django_utils.cache.middleware.TieredCacheMiddleware',
    # Outputs monitoring metrics for a request.
    'edx_rest_framework_extensions.middleware.RequestCustomAttributesMiddleware',
    # Ensures proper DRF permissions in support of JWTs
    'edx_rest_framework_extensions.auth.jwt.middleware.EnsureJWTAuthSettingsMiddleware',
    # Track who made each change to a model using HistoryRequestMiddleware
    'simple_history.middleware.HistoryRequestMiddleware',
    # Used by custom django-rules predicates.
    'crum.CurrentRequestUserMiddleware',
)

# https://github.com/dabapps/django-log-request-id
LOG_REQUEST_ID_HEADER = "HTTP_X_REQUEST_ID"
GENERATE_REQUEST_ID_IF_NOT_IN_HEADER = False
REQUEST_ID_RESPONSE_HEADER = "X-Request-ID"
NO_REQUEST_ID = "None"
LOG_REQUESTS = True

# Enable CORS
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = corsheaders_default_headers + (
    'use-jwt-cookie',
)
CORS_ORIGIN_WHITELIST = []

ROOT_URLCONF = 'enterprise_subsidy.urls'

# Python dotted path to the WSGI application used by Django's runserver.
WSGI_APPLICATION = 'enterprise_subsidy.wsgi.application'

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
# Set this value in the environment-specific files (e.g. local.py, production.py, test.py)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.',
        'NAME': '',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',  # Empty for localhost through domain sockets or '127.0.0.1' for localhost through TCP.
        'PORT': '',  # Set to empty string for default.
    }
}

# New DB primary keys default to an IntegerField.
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Django Rest Framework
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'PAGE_SIZE': 10,
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
}

# This is what populates the core.User.lms_user_id field.
EDX_DRF_EXTENSIONS = {
    "JWT_PAYLOAD_USER_ATTRIBUTE_MAPPING": {
        "administrator": "is_staff",
        "email": "email",
        "full_name": "full_name",
        "user_id": "lms_user_id",
    },
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Enterprise Subsidy API',
    'DESCRIPTION': 'API for controlling disbursement of value for ledger-based subsidy records.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE': False,
    'TAGS': [
        {
            'name': 'subsidy',
            'description': '<h3>All endpoints that query or command directly against Subsidy records.</h3>',
        },
        {
            'name': 'transactions',
            'description': '<h3>All endpoints that query or command directly against Transaction records</h3>.',
        },
        {
            'name': 'api',
            'description': '<h3>All endpoints not tagged by anything else.</h3>',
        },
    ],
}

# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Django 4.0+ uses zoneinfo if this is not set. We can remove this and
# migrate to zoneinfo after Django 4.2 upgrade. See more on following url
# https://docs.djangoproject.com/en/4.2/releases/4.0/#zoneinfo-default-timezone-implementation
USE_DEPRECATED_PYTZ = True

LOCALE_PATHS = (
    root('conf', 'locale'),
)


# MEDIA CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = root('media')

# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = '/media/'
# END MEDIA CONFIGURATION


# STATIC FILE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = root('assets')

# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = '/static/'

# See: https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = (
    root('static'),
)

# TEMPLATE CONFIGURATION
# See: https://docs.djangoproject.com/en/3.2/ref/settings/#templates
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'DIRS': (
            root('templates'),
        ),
        'OPTIONS': {
            'context_processors': (
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.request',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.contrib.messages.context_processors.messages',
                'enterprise_subsidy.apps.core.context_processors.core',
            ),
            'debug': True,  # Django will only display debug pages if the global DEBUG setting is set to True.
        }
    },
]
# END TEMPLATE CONFIGURATION


# COOKIE CONFIGURATION
# The purpose of customizing the cookie names is to avoid conflicts when
# multiple Django services are running behind the same hostname.
# Detailed information at: https://docs.djangoproject.com/en/dev/ref/settings/
SESSION_COOKIE_NAME = 'enterprise_subsidy_sessionid'
CSRF_COOKIE_NAME = 'enterprise_subsidy_csrftoken'
LANGUAGE_COOKIE_NAME = 'enterprise_subsidy_language'
# END COOKIE CONFIGURATION

CSRF_COOKIE_SECURE = False
CSRF_TRUSTED_ORIGINS = []

# AUTHENTICATION CONFIGURATION
LOGIN_URL = '/login/'
LOGOUT_URL = '/logout/'

AUTH_USER_MODEL = 'core.User'

AUTHENTICATION_BACKENDS = (
    'auth_backends.backends.EdXOAuth2',
    'rules.permissions.ObjectPermissionBackend',
    'django.contrib.auth.backends.ModelBackend',
)

ENABLE_AUTO_AUTH = False
AUTO_AUTH_USERNAME_PREFIX = 'auto_auth_'

SOCIAL_AUTH_STRATEGY = 'auth_backends.strategies.EdxDjangoStrategy'

# Set these to the correct values for your OAuth2 provider (e.g., LMS)
SOCIAL_AUTH_EDX_OAUTH2_KEY = 'replace-me'
SOCIAL_AUTH_EDX_OAUTH2_SECRET = 'replace-me'
SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT = 'replace-me'
SOCIAL_AUTH_EDX_OAUTH2_LOGOUT_URL = 'replace-me'
BACKEND_SERVICE_EDX_OAUTH2_KEY = 'replace-me'
BACKEND_SERVICE_EDX_OAUTH2_SECRET = 'replace-me'

JWT_AUTH = {
    'JWT_AUTH_HEADER_PREFIX': 'JWT',
    'JWT_ISSUER': 'http://127.0.0.1:8000/oauth2',
    'JWT_ALGORITHM': 'HS256',
    'JWT_VERIFY_EXPIRATION': True,
    'JWT_PAYLOAD_GET_USERNAME_HANDLER': lambda d: d.get('preferred_username'),
    'JWT_LEEWAY': 1,
    'JWT_DECODE_HANDLER': 'edx_rest_framework_extensions.auth.jwt.decoder.jwt_decode_handler',
    'JWT_PUBLIC_SIGNING_JWK_SET': None,
    'JWT_AUTH_COOKIE': 'edx-jwt-cookie',
    'JWT_AUTH_COOKIE_HEADER_PAYLOAD': 'edx-jwt-cookie-header-payload',
    'JWT_AUTH_COOKIE_SIGNATURE': 'edx-jwt-cookie-signature',
    'JWT_SECRET_KEY': 'SET-ME-PLEASE',
    # JWT_ISSUERS enables token decoding for multiple issuers (Note: This is not a native DRF-JWT field)
    # We use it to allow different values for the 'ISSUER' field, but keep the same SECRET_KEY and
    # AUDIENCE values across all issuers.
    'JWT_ISSUERS': [
        {
            'AUDIENCE': 'SET-ME-PLEASE',
            'ISSUER': 'http://localhost:18000/oauth2',
            'SECRET_KEY': 'SET-ME-PLEASE'
        },
    ],
}

# Request the user's permissions in the ID token
EXTRA_SCOPE = ['permissions']

LOGIN_REDIRECT_URL = '/api/schema/swagger-ui/'
# END AUTHENTICATION CONFIGURATION

# Set up system-to-feature roles mapping for edx-rbac.
SYSTEM_TO_FEATURE_ROLE_MAPPING = {
    SYSTEM_ENTERPRISE_LEARNER_ROLE: [ENTERPRISE_SUBSIDY_LEARNER_ROLE],
    SYSTEM_ENTERPRISE_ADMIN_ROLE: [ENTERPRISE_SUBSIDY_LEARNER_ROLE, ENTERPRISE_SUBSIDY_ADMIN_ROLE],
    SYSTEM_ENTERPRISE_OPERATOR_ROLE: [
        ENTERPRISE_SUBSIDY_LEARNER_ROLE, ENTERPRISE_SUBSIDY_ADMIN_ROLE, ENTERPRISE_SUBSIDY_OPERATOR_ROLE
    ],
    # The catalog admin role doesn't award any permissions in the subsidy service.
    SYSTEM_ENTERPRISE_CATALOG_ADMIN_ROLE: [],
}


# OPENEDX-SPECIFIC CONFIGURATION
PLATFORM_NAME = 'Your Platform Name Here'
# END OPENEDX-SPECIFIC CONFIGURATION

# Set up logging for development use (logging to stdout)
LOGGING = get_logger_config(debug=DEBUG)


# Application settings
ALLOW_LEDGER_MODIFICATION = False

# per-view cache timeout settings
# We can disable caching on this view by setting the value below to 0.
CONTENT_METADATA_VIEW_CACHE_TIMEOUT_SECONDS = 60 * 15

# disable indexing on history_date
SIMPLE_HISTORY_DATE_INDEX = False


# How long we keep API Client data in cache. (seconds)
ONE_HOUR = 60 * 60
LMS_USER_DATA_CACHE_TIMEOUT = ONE_HOUR

# Defines error bounds for requested redemption price validation
# See https://github.com/openedx/enterprise-access/blob/main/docs/decisions/0014-assignment-price-validation.rst
# We use a wider default allowed interval in this service, because
# generally only operators are allowed to make calls to redeem, and there may
# be more drift between the time of allocation and the time of redemption.
ALLOCATION_PRICE_VALIDATION_LOWER_BOUND_RATIO = .80
ALLOCATION_PRICE_VALIDATION_UPPER_BOUND_RATIO = 1.20

# Kafka and event broker settings
TRANSACTION_LIFECYCLE_TOPIC = "enterprise-subsidies-transaction-lifecycle"
TRANSACTION_CREATED_EVENT_NAME = "org.openedx.enterprise.subsidy_ledger_transaction.created.v1"
TRANSACTION_COMMITTED_EVENT_NAME = "org.openedx.enterprise.subsidy_ledger_transaction.committed.v1"
TRANSACTION_FAILED_EVENT_NAME = "org.openedx.enterprise.subsidy_ledger_transaction.failed.v1"
TRANSACTION_REVERSED_EVENT_NAME = "org.openedx.enterprise.subsidy_ledger_transaction.reversed.v1"

# .. setting_name: EVENT_BUS_PRODUCER_CONFIG
# .. setting_default: all events disabled
# .. setting_description: Dictionary of event_types mapped to dictionaries of topic to topic-related configuration.
#    Each topic configuration dictionary contains
#    * `enabled`: a toggle denoting whether the event will be published to the topic. These should be annotated
#       according to
#       https://edx.readthedocs.io/projects/edx-toggles/en/latest/how_to/documenting_new_feature_toggles.html
#    * `event_key_field` which is a period-delimited string path to event data field to use as event key.
#    Note: The topic names should not include environment prefix as it will be dynamically added based on
#    EVENT_BUS_TOPIC_PREFIX setting.
EVENT_BUS_PRODUCER_CONFIG = {
    TRANSACTION_CREATED_EVENT_NAME: {
        TRANSACTION_LIFECYCLE_TOPIC: {
            'event_key_field': 'ledger_transaction.uuid',
            'enabled': False,
        },
    },
    TRANSACTION_COMMITTED_EVENT_NAME: {
        TRANSACTION_LIFECYCLE_TOPIC: {
            'event_key_field': 'ledger_transaction.uuid',
            'enabled': False,
        },
    },
    TRANSACTION_FAILED_EVENT_NAME: {
        TRANSACTION_LIFECYCLE_TOPIC: {
            'event_key_field': 'ledger_transaction.uuid',
            'enabled': False,
        },
    },
    TRANSACTION_REVERSED_EVENT_NAME: {
        TRANSACTION_LIFECYCLE_TOPIC: {
            'event_key_field': 'ledger_transaction.uuid',
            'enabled': False,
        },
    },
}

# FEATURE FLAGS CONFIGURATION

# Enable handling of the LEARNER_CREDIT_COURSE_ENROLLMENT_REVOKED event, which triggers
# writing of a reversal on learner-initiated unenrollment.
ENABLE_HANDLE_LC_ENROLLMENT_REVOKED = False

# END FEATURE FLAGS CONFIGURATION
