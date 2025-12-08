⚠️ **DEPRECATION NOTICE**
#########################

This repository is **deprecated** and no longer actively developed.

- 2U maintains a fork located at `edx/enterprise-subsidy <https://github.com/edx/enterprise-subsidy>`_
- If you or your organization wants to adop maintenance of openedx/enterprise-subsidy,
  please reach out to OpenEdx via `Slack <https://openedx.org/slack>`_.

Original README
################

enterprise_subsidy
##################

|ci-badge| |codecov-badge| |license-badge| |status-badge|

Purpose
*******

Captures and balances enterprise-subsidized transactions.

Getting Started
***************

Developing
==========

One Time Setup
--------------
.. code-block::

  # Clone the repository
  git clone git@github.com:openedx/enterprise-subsidy.git
  cd enterprise-subsidy
  make dev.up.build-no-cache
  ./provision-enterprise-subsidy.sh

Go visit http://localhost:18280/admin/ and login with the standard edx/edx credentials to confirm
that provisioning was successful.

Every time you develop something in this repo
---------------------------------------------
.. code-block::

  # Grab the latest code
  git checkout main
  git pull

  # start the docker containers
  make dev.up.build # or docker-compose build --no-cache && make dev.up

  # enter the app container shell
  make app-shell

  # Install/update the dev requirements
  make requirements

  # Run the tests and quality checks (to verify the status before you make any changes)
  make test
  # optionally make validate

  # Now, back on your host...
  # Make a new branch for your changes
  git checkout -b <your_github_username>/<short_description>

  # Using your favorite editor, edit the code to make your change.
  # vim ...

  # Run your new tests
  make app-shell
  pytest ./path/to/new/tests

  # Run all the tests and quality checks
  make validate

  # Commit all your changes
  # exit to your host again
  git commit ...
  git push

  # Open a PR and ask for review.

Setting up openedx-events
-------------------------
Ensure you've installed the ``edx_event_bus_kafka`` and ``openedx_events`` requirements. Entering
a shell with ``make app-shell`` and then running ``make requirements`` should install these for you.

From your host, run ``make dev.up.with-events``, which will start a local kafka container for you.
Visit http://localhost:9021/clusters to access the local "Confluent Control Center".
Confluent is like a cloud wrapper around vanilla Kafka.

Your ``devstack.py`` settings should already be configured to point at this event broker,
and to configure enterprise-subsidy as an openedx event consumer and/or produer.

Start by switching over to your **enterprise-access** repo and make sure it has requirements installed.
We have a specific enterprise "ping" event and management command defined to test
that your local event bus is well-configured. Open a shell with ``make app-shell`` and run::

  ./manage.py consume_enterprise_ping_events

This will consume ping events from the ``dev-enterprise-core`` topic.
You may see a ``Broker: Unknown topic`` error the first time you run it.  When you run your
test event production below, that error will resolve (producing the event creates the topic
if it does not exist). **Leave the consumer running.** You should see the ``enterprise-access-service``
as a registered consumer in your local confluent control center.

Now, go back to your **enterprise-subsidy** directory. Make sure requirements are installed,
specifically the ``edx_event_bus_kafka`` and ``openedx_events`` packages. Use ``make app-shell``
in this repo and we'll *produce* a ping event::

  ./manage.py produce_enterprise_ping_event

If this event was successfully produced, you'll see a log message that says
``Message delivered to Kafka event bus: topic=dev-events-testing``.
You should also now see the ``dev-events-testing`` topic available in your local confluent control center,
in addition to the test events that are being published to the topic.

Deploying
=========
Merging a pull request will cause a GoCD `build` pipeline to start automatically.
When the build pipeline is completed, the built image will be deployed to our staging
environment automatically.

To deploy your change to the production environment, you must manually trigger
the production `enterprise-subsidy-prod` pipeline, which will use the latest
commit in the ``main`` branch by default.

Getting Help
************

Documentation
=============

* https://github.com/openedx/enterprise-subsidy/tree/main/docs/decisions documents
  various architectural decisions the maintainers have made.
* https://github.com/openedx/enterprise-subsidy/tree/main/docs/caching.rst describes the design and use of
  caching layers in this service.

More Help
=========

If you're having trouble, we have discussion forums at
https://discuss.openedx.org where you can connect with others in the
community.

Our real-time conversations are on Slack. You can request a `Slack
invitation`_, then join our `community Slack workspace`_.

For anything non-trivial, the best path is to open an issue in this
repository with as many details about the issue you are facing as you
can provide.

https://github.com/openedx/enterprise-subsidy/issues

For more information about these options, see the `Getting Help`_ page.

.. _Slack invitation: https://openedx.org/slack
.. _community Slack workspace: https://openedx.slack.com/
.. _Getting Help: https://openedx.org/getting-help

License
*******

The code in this repository is licensed under the AGPL 3.0 unless
otherwise noted.

Please see `LICENSE.txt <LICENSE.txt>`_ for details.

Contributing
************

Contributions are very welcome.
Please read `How To Contribute <https://openedx.org/r/how-to-contribute>`_ for details.

This project is currently accepting all types of contributions, bug fixes,
security fixes, maintenance work, or new features.  However, please make sure
to have a discussion about your new feature idea with the maintainers prior to
beginning development to maximize the chances of your change being accepted.
You can start a conversation by creating a new issue on this repo summarizing
your idea.

The Open edX Code of Conduct
****************************

All community members are expected to follow the `Open edX Code of Conduct`_.

.. _Open edX Code of Conduct: https://openedx.org/code-of-conduct/

People
******

The assigned maintainers for this component and other project details may be
found in `Backstage`_. Backstage pulls this data from the ``catalog-info.yaml``
file in this repo.

.. _Backstage: https://open-edx-backstage.herokuapp.com/catalog/default/component/enterprise-subsidy

Reporting Security Issues
*************************

Please do not report security issues in public. Please email security@openedx.org.

.. |ci-badge| image:: https://github.com/openedx/enterprise-subsidy/workflows/Python%20CI/badge.svg?branch=main
    :target: https://github.com/openedx/enterprise-subsidy/actions
    :alt: CI

.. |codecov-badge| image:: https://codecov.io/github/openedx/enterprise-subsidy/coverage.svg?branch=main
    :target: https://codecov.io/github/openedx/enterprise-subsidy?branch=main
    :alt: Codecov

.. |license-badge| image:: https://img.shields.io/github/license/openedx/enterprise-subsidy.svg
    :target: https://github.com/openedx/enterprise-subsidy/blob/main/LICENSE.txt
    :alt: License

.. |status-badge| image:: https://img.shields.io/badge/Status-Maintained-brightgreen
