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
