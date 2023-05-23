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
