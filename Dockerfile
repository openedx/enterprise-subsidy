FROM ubuntu:focal as app
MAINTAINER sre@edx.org

# Packages installed:

# language-pack-en locales; ubuntu locale support so that system utilities have a consistent
# language and time zone.

# python; ubuntu doesnt ship with python, so this is the python we will use to run the application

# python3-pip; install pip to install application requirements.txt files

# libmysqlclient-dev; to install header files needed to use native C implementation for
# MySQL-python for performance gains.

# libssl-dev; # mysqlclient wont install without this.

# python3-dev; to install header files for python extensions; much wheel-building depends on this

# gcc; for compiling python extensions distributed with python packages like mysql-client

# git; necessary to install local python packages in editable mode via pip.  It's got electrolytes.

# make; we use makefiles for all sorts of stuff

# If you add a package here please include a comment above describing what it is used for
RUN apt-get update && apt-get -qy install --no-install-recommends \
 language-pack-en \
 locales \
 python3.8 \
 python3-pip \
 python3.8-venv \
 libmysqlclient-dev \
 libssl-dev \
 python3.8-dev \
 gcc \
 git \
 make

# delete apt package lists because we do not need them inflating our image
RUN rm -rf /var/lib/apt/lists/*

# Create a virtualenv for sanity
ENV VIRTUAL_ENV=/edx/venvs/enterprise-subsidy
RUN python3.8 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN locale-gen en_US.UTF-8
ENV LANG en_US.UTF-8
ENV LANGUAGE en_US:en
ENV LC_ALL en_US.UTF-8
ENV DJANGO_SETTINGS_MODULE enterprise_subsidy.settings.production

EXPOSE 18280
RUN useradd -m --shell /bin/false app

WORKDIR /edx/app/enterprise-subsidy
RUN git config --global --add safe.directory /edx/app/enterprise-subsidy

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
