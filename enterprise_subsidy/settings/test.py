import os

from enterprise_subsidy.settings.base import *

# IN-MEMORY TEST DATABASE
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    },
}
# END IN-MEMORY TEST DATABASE

ENTERPRISE_SUBSIDY_URL = 'http://enterprise-subsidy.app:18280'
FRONTEND_APP_LEARNING_URL = 'http://localhost:2000'

GET_SMARTER_API_URL = 'http://getsmarter.com/enterprise/allocate'
GET_SMARTER_OAUTH2_KEY = 'get-smarter-key'
GET_SMARTER_OAUTH2_SECRET = 'get-smarter-secret'
GET_SMARTER_OAUTH2_PROVIDER_URL = 'https://get-smarter.provider.url'

# Kafka Settings
# We set to fake server addresses because we shouldn't actually be emitting real events during tests
EVENT_BUS_KAFKA_SCHEMA_REGISTRY_URL = 'http://test.schema-registry:8000'
EVENT_BUS_KAFKA_BOOTSTRAP_SERVERS = 'test.kafka:8001'
EVENT_BUS_PRODUCER = 'edx_event_bus_kafka.create_producer'
EVENT_BUS_CONSUMER = 'edx_event_bus_kafka.KafkaEventConsumer'
EVENT_BUS_TOPIC_PREFIX = 'dev-test'

EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_CREATED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_COMMITTED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_FAILED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
EVENT_BUS_PRODUCER_CONFIG[TRANSACTION_REVERSED_EVENT_NAME][TRANSACTION_LIFECYCLE_TOPIC]['enabled'] = True
