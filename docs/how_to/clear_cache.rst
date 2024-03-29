Manually clear Django cache 
===========================

At times, it is helpful to clear the cache for the application to enable more efficient QA in local/stage/production environments 
when working with APIs that cache data from external sources. For instance, enterprise-subsidy makes an API request to enterprise-catalog to
retrieve metadata about the enterprise catalog and caches it for 30 minutes.

In order to get around this, `django-clearcache` (https://github.com/timonweb/django-clearcache) is installed and configured, which allows you to clear the cache for the application via
Django and via a manage.py command.

Via Django admin
----------------

1. Go to /admin/clearcache/, you should see a form with cache selector
2. Pick a cache. Usually there's one default cache, but can be more.
3. Click the button, you're done!

Via manage.py command
---------------------

1. Run the following command to clear the default cache

.. code-block:: bash

    $ python manage.py clearcache

2. Run the command above with an additional parameter to clear non-default cache (if exists):

.. code-block:: bash

    $ python manage.py clearcache cache_name
