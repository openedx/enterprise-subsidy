FROM ubuntu:focal as app
MAINTAINER sre@edx.org

# Packages installed:

# language-pack-en locales; ubuntu locale support so that system utilities have a consistent
# language and time zone.

# python; ubuntu doesnt ship with python, so this is the python we will use to run the application

# python3-pip; install pip to install application requirements.txt files

# pkg-config
#     mysqlclient>=2.2.0 requires this (https://github.com/PyMySQL/mysqlclient/issues/620)

# libmysqlclient-dev; to install header files needed to use native C implementation for
# MySQL-python for performance gains.

# libssl-dev; # mysqlclient wont install without this.

# python3-dev; to install header files for python extensions; much wheel-building depends on this

# gcc; for compiling python extensions distributed with python packages like mysql-client

# git; necessary to install local python packages in editable mode via pip.  It's got electrolytes.

# make; we use makefiles for all sorts of stuff

# ENV variables for Python 3.12 support
ARG PYTHON_VERSION=3.12
ENV TZ=UTC
ENV TERM=xterm-256color
ENV DEBIAN_FRONTEND=noninteractive

# software-properties-common is needed to setup Python 3.12 env
RUN apt-get update && \
  apt-get install -y software-properties-common && \
  apt-add-repository -y ppa:deadsnakes/ppa

# If you add a package here please include a comment above describing what it is used for
RUN apt-get update && apt-get -qy install --no-install-recommends \
 build-essential \
 language-pack-en \
 locales \
 pkg-config \
 libmysqlclient-dev \
 libssl-dev \
 gcc \
 git \
 make \
 curl \
 libffi-dev \
 libsqlite3-dev \
 python3-pip \
 python${PYTHON_VERSION} \
 python${PYTHON_VERSION}-dev \
 python${PYTHON_VERSION}-distutils 

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# delete apt package lists because we do not need them inflating our image
RUN rm -rf /var/lib/apt/lists/*

# need to use virtualenv pypi package with Python 3.12
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python${PYTHON_VERSION}
RUN pip install virtualenv

# Create a virtualenv for sanity
ENV VIRTUAL_ENV=/edx/venvs/enterprise-subsidy
RUN virtualenv -p python${PYTHON_VERSION} $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV DJANGO_SETTINGS_MODULE enterprise_subsidy.settings.production

EXPOSE 18280
RUN useradd -m --shell /bin/false app

WORKDIR /edx/app/enterprise-subsidy

# Copy the requirements explicitly even though we copy everything below
# this prevents the image cache from busting unless the dependencies have changed.
COPY requirements/production.txt /edx/app/enterprise-subsidy/requirements/production.txt
COPY requirements/pip.txt /edx/app/enterprise-subsidy/requirements/pip.txt

# Dependencies are installed as root so they cannot be modified by the application user.
RUN pip install -r requirements/pip.txt
RUN pip install -r requirements/production.txt

RUN mkdir -p /edx/var/log

# Code is owned by root so it cannot be modified by the application user.
# So we copy it before changing users.
USER app

# Gunicorn 19 does not log to stdout or stderr by default. Once we are past gunicorn 19, the logging to STDOUT need not be specified.
CMD gunicorn --workers=2 --name enterprise-subsidy -c /edx/app/enterprise-subsidy/enterprise_subsidy/docker_gunicorn_configuration.py --log-file - --max-requests=1000 enterprise_subsidy.wsgi:application

# This line is after the requirements so that changes to the code will not
# bust the image cache
COPY . /edx/app/enterprise-subsidy

FROM app as newrelic
RUN pip install newrelic
CMD gunicorn --workers=2 --name enterprise-subsidy -c /edx/app/enterprise-subsidy/enterprise_subsidy/docker_gunicorn_configuration.py --log-file - --max-requests=1000 enterprise_subsidy.wsgi:application

FROM app as devstack
USER root
COPY requirements/dev.txt /edx/app/enterprise-subsidy/requirements/dev.txt
RUN pip install -r requirements/dev.txt
USER app
CMD gunicorn --workers=2 --name enterprise-subsidy -c /edx/app/enterprise-subsidy/enterprise_subsidy/docker_gunicorn_configuration.py --log-file - --max-requests=1000 enterprise_subsidy.wsgi:application
