"""
Root API URLs.

All API URLs should be versioned, so urlpatterns should only
contain namespaces for the active versions of the API.
"""
from django.urls import include, re_path

from enterprise_subsidy.apps.api.v1 import urls as v1_urls
from enterprise_subsidy.apps.api.v2 import urls as v2_urls

app_name = 'api'
urlpatterns = [
    re_path(r'^v1/', include(v1_urls)),
    re_path(r'^v2/', include(v2_urls)),
]
