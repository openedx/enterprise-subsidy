from enterprise_subsidy.settings.base import *

ALLOWED_HOSTS = ['*']

DEBUG = True

# CACHE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
# END CACHE CONFIGURATION

# DATABASE CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': root('default.db'),
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}
# END DATABASE CONFIGURATION

# EMAIL CONFIGURATION
# See: https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# END EMAIL CONFIGURATION

# TOOLBAR CONFIGURATION
# See: https://django-debug-toolbar.readthedocs.org/en/latest/installation.html
if os.environ.get('ENABLE_DJANGO_TOOLBAR', False):
    INSTALLED_APPS += (
        'debug_toolbar',
    )

    MIDDLEWARE += (
        'debug_toolbar.middleware.DebugToolbarMiddleware',
    )

    DEBUG_TOOLBAR_PATCH_SETTINGS = False

INTERNAL_IPS = ('127.0.0.1',)
# END TOOLBAR CONFIGURATION

# AUTHENTICATION
# Use a non-SSL URL for authorization redirects
SOCIAL_AUTH_REDIRECT_IS_HTTPS = False

# Generic OAuth2 variables irrespective of SSO/backend service key types.
OAUTH2_PROVIDER_URL = 'http://localhost:18000/oauth2'

JWT_AUTH.update({
    'JWT_ALGORITHM': 'HS256',
    'JWT_SECRET_KEY': SOCIAL_AUTH_EDX_OAUTH2_SECRET,
    'JWT_ISSUER': OAUTH2_PROVIDER_URL,
    'JWT_AUDIENCE': SOCIAL_AUTH_EDX_OAUTH2_KEY,
})

ENABLE_AUTO_AUTH = True

LOGGING = get_logger_config(debug=DEBUG, format_string=LOGGING_FORMAT_STRING)

# Shell plus
# https://django-extensions.readthedocs.io/en/latest/shell_plus.html#interactive-python-shells
INSTALLED_APPS += ('django_extensions',)
SHELL_PLUS_DONT_LOAD = ['HistoricalSubsidy', ]
# SHELL_PLUS = 'ipython'

#####################################################################
# Lastly, see if the developer has any local overrides.
if os.path.isfile(join(dirname(abspath(__file__)), 'private.py')):
    from .private import *  # pylint: disable=import-error
