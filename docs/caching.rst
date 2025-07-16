Cache design and use
####################

Cache layers
************

We utilize both a ``RequestCache`` and ``TieredCache`` provided by
https://github.com/openedx/edx-django-utils/tree/master/edx_django_utils/cache.
The RequestCache is a request-scoped dictionary that stores keys and their values
and exists only for the lifetime of a given request.
TieredCache combines a RequestCache with the default Django cache, which for enterprise-subsidy
is memcached.

Versioned cache keys
********************

We use versioned cache keys to support key-based cache invalidation.
See https://signalvnoise.com/posts/3113-how-key-based-cache-expiration-works for background on this design.

Our cache key version currently consists of two components: the ``enterprise_subsidy`` package version
defined in ``enterprise_subsidy.__init__.py``, and an optional Django settings called ``CACHE_KEY_VERSION_STAMP``.

This optional settings-based component can be changed to effectively invalidate **every** cache
key in the Django-memcached server in whatever environment the setting is defined in.  The value
itself isn't particularly important, something like a datetime string will work fine.

.. code-block::

   # In your environment's Django settings file.
   CACHE_KEY_VERSION_STAMP = '20230607123455'

In the future, we hope to incorporate upstream changes to data in the enterprise-catalog service
into our key-based invalidation scheme, so that the timeouts described below become unnecessary to maintain.

Where we cache
**************

``ContentMetadataApi``
======================
We utilize a TieredCache to store the content metadata details for a given
content identifier.  The memcached timeout defaults to 30 minutes, but can be modified
with the settings variable ``CONTENT_METADATA_CACHE_TIMEOUT`` in your environment's settings.
The value should be an integer representing the Django-memcached timeout in seconds.

.. code-block::

   # In your environment's Django settings file.
   CONTENT_METADATA_CACHE_TIMEOUT = 60 * 45  # Make the cache timeout 45 minutes


``ContentMetadataViewSet``
==========================
We cache the result of calls to the ``/api/v1/content-metadata/{Content Identifier}/`` page
for 60 seconds by default using Django's ``django.views.decorators.cache.cache_page`` decorator.
This timeout can be configured via your environment's settings using the variable
``CONTENT_METADATA_VIEW_CACHE_TIMEOUT_SECONDS``, which should be an integer representing
the Django-memcached timeout in seconds.

.. code-block::

   # In your environment's Django settings file.
   CONTENT_METADATA_VIEW_CACHE_TIMEOUT_SECONDS = 60 * 13  # Make the cache timeout 13 minutes
