from enterprise_subsidy.settings.local import *

CORS_ORIGIN_WHITELIST = (
    'http://localhost:18450',  # frontend-app-support-tools
    'http://localhost:8734',  # frontend-app-learner-portal-enterprise
    'http://localhost:1991',  # frontend-app-admin-portal
)

CSRF_TRUSTED_ORIGINS = [
    'http://localhost:18450',
    'http://localhost:8734',
    'http://localhost:1991',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'enterprise_subsidy'),
        'USER': os.environ.get('DB_USER', 'root'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'enterprise-subsidy.mysql80'),
        'PORT': os.environ.get('DB_PORT', 3306),
        'ATOMIC_REQUESTS': False,
        'CONN_MAX_AGE': 60,
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.PyMemcacheCache',
        'LOCATION': 'enterprise-subsidy.memcache:11211',
    }

}

INSTALLED_APPS += (
    'edx_event_bus_kafka',
)

# Generic OAuth2 variables irrespective of SSO/backend service key types.
OAUTH2_PROVIDER_URL = 'http://edx.devstack.lms:18000/oauth2'

# OAuth2 variables specific to social-auth/SSO login use case.
SOCIAL_AUTH_EDX_OAUTH2_KEY = os.environ.get('SOCIAL_AUTH_EDX_OAUTH2_KEY', 'enterprise-subsidy-sso-key')
SOCIAL_AUTH_EDX_OAUTH2_SECRET = os.environ.get('SOCIAL_AUTH_EDX_OAUTH2_SECRET', 'enterprise-subsidy-sso-secret')
SOCIAL_AUTH_EDX_OAUTH2_ISSUER = os.environ.get('SOCIAL_AUTH_EDX_OAUTH2_ISSUER', 'http://localhost:18000')
SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT = os.environ.get('SOCIAL_AUTH_EDX_OAUTH2_URL_ROOT', 'http://edx.devstack.lms:18000')
SOCIAL_AUTH_EDX_OAUTH2_LOGOUT_URL = os.environ.get('SOCIAL_AUTH_EDX_OAUTH2_LOGOUT_URL', 'http://localhost:18000/logout')
SOCIAL_AUTH_EDX_OAUTH2_PUBLIC_URL_ROOT = os.environ.get(
    'SOCIAL_AUTH_EDX_OAUTH2_PUBLIC_URL_ROOT', 'http://localhost:18000',
)

# OAuth2 variables specific to backend service API calls.
BACKEND_SERVICE_EDX_OAUTH2_KEY = os.environ.get(
    'BACKEND_SERVICE_EDX_OAUTH2_KEY', 'enterprise-subsidy-backend-service-key'
)
BACKEND_SERVICE_EDX_OAUTH2_SECRET = os.environ.get(
    'BACKEND_SERVICE_EDX_OAUTH2_SECRET', 'enterprise-subsidy-backend-service-secret'
)

JWT_AUTH.update({
    'JWT_SECRET_KEY': 'lms-secret',
    'JWT_ISSUER': 'http://localhost:18000/oauth2',
    'JWT_AUDIENCE': None,
    'JWT_VERIFY_AUDIENCE': False,
    'JWT_PUBLIC_SIGNING_JWK_SET': (
        '{"keys": [{"kid": "devstack_key", "e": "AQAB", "kty": "RSA", "n": "smKFSYowG6nNUAdeqH1jQQnH1PmIHphzBmwJ5vRf1vu'
        '48BUI5VcVtUWIPqzRK_LDSlZYh9D0YFL0ZTxIrlb6Tn3Xz7pYvpIAeYuQv3_H5p8tbz7Fb8r63c1828wXPITVTv8f7oxx5W3lFFgpFAyYMmROC'
        '4Ee9qG5T38LFe8_oAuFCEntimWxN9F3P-FJQy43TL7wG54WodgiM0EgzkeLr5K6cDnyckWjTuZbWI-4ffcTgTZsL_Kq1owa_J2ngEfxMCObnzG'
        'y5ZLcTUomo4rZLjghVpq6KZxfS6I1Vz79ZsMVUWEdXOYePCKKsrQG20ogQEkmTf9FT_SouC6jPcHLXw"}]}'
    ),
    'JWT_ISSUERS': [{
        'AUDIENCE': 'lms-key',
        'ISSUER': 'http://localhost:18000/oauth2',
        'SECRET_KEY': 'lms-secret',
    }],
})

LMS_URL = 'http://edx.devstack.lms:18000'
ENTERPRISE_CATALOG_URL = 'http://enterprise.catalog.app:18160'
ENTERPRISE_SUBSIDY_URL = 'http://localhost:18280'
FRONTEND_APP_LEARNING_URL = 'http://localhost:2000'

# Kafka Settings
# "Standard" Kafka settings as defined in https://github.com/openedx/event-bus-kafka/tree/main
EVENT_BUS_KAFKA_SCHEMA_REGISTRY_URL = 'http://edx.devstack.schema-registry:8081'
EVENT_BUS_KAFKA_BOOTSTRAP_SERVERS = 'edx.devstack.kafka:29092'
EVENT_BUS_PRODUCER = 'edx_event_bus_kafka.create_producer'
EVENT_BUS_CONSUMER = 'edx_event_bus_kafka.KafkaEventConsumer'
EVENT_BUS_TOPIC_PREFIX = 'dev'

EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_CREATED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_COMMITTED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_FAILED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_REVERSED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True

# Private settings
# The local.py settings file also does this, but then this current file (devstack.py)
# imports *from* local.py, so anything earlier in this file overrides what's in private.py
# We want private.py to have the highest precedence, so re-import private settings again here.
if os.path.isfile(join(dirname(abspath(__file__)), 'private.py')):
    from .private import *  # pylint: disable=import-error
