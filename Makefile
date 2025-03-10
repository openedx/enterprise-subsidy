.DEFAULT_GOAL := help

.PHONY: help clean requirements ci_requirements dev_requirements \
        validation_requirements doc_requirements production-requirements static shell \
        test coverage isort_check isort style lint quality pii_check validate \
        migrate html_coverage upgrade extract_translation dummy_translations \
        compile_translations fake_translations pull_translations \
        push_translations start-devstack open-devstack pkg-devstack \
        detect_changed_source_translations validate_translations check_keywords \
        install_transifex_client

define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

# Generates a help message. Borrowed from https://github.com/pydanny/cookiecutter-djangopackage.
help: ## display this help message
	@echo "Please use \`make <target>\` where <target> is one of"
	@awk -F ':.*?## ' '/^[a-zA-Z]/ && NF==2 {printf "\033[36m  %-25s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

clean: ## delete generated byte code and coverage reports
	find . -name '*.pyc' -delete
	coverage erase
	rm -rf assets
	rm -rf pii_report
	rm -rf reserved_keywords_report

requirements: dev_requirements ## sync to default requirements

ci_requirements: validation_requirements ## sync to requirements needed for CI checks

pip_requirements:  ## install pip-sync
	pip install -r requirements/pip-tools.txt

dev_requirements: pip_requirements ## sync to requirements for local development
	pip-sync -q requirements/dev.txt requirements/private.* requirements/test.txt

validation_requirements: pip_requirements ## sync to requirements for testing & code quality checking
	pip-sync -q requirements/validation.txt

doc_requirements:
	pip-sync -q requirements/doc.txt

production-requirements: pip_requirements ## install requirements for production
	pip-sync -q requirements/production.txt

static: ## generate static files
	python manage.py collectstatic --noinput

shell: ## run Django shell
	python manage.py shell

test: clean ## run tests and generate coverage report
	pytest

# To be run from CI context
coverage: clean
	pytest --cov-report html
	$(BROWSER) htmlcov/index.html

isort_check: ## check that isort has been run
	isort --check-only enterprise_subsidy/

isort: ## run isort to sort imports in all Python files
	isort --recursive --atomic enterprise_subsidy/

style: ## run Python style checker
	pycodestyle enterprise_subsidy manage.py

lint: ## run Python code linting
	pylint --rcfile=pylintrc enterprise_subsidy *.py

pylint: lint

quality:
	tox -e quality

pii_check: ## check for PII annotations on all Django models
	DJANGO_SETTINGS_MODULE=enterprise_subsidy.settings.test \
	code_annotations django_find_annotations --config_file .pii_annotations.yml --lint --report --coverage

check_keywords: ## Scan the Django models in all installed apps in this project for restricted field names
	mkdir -p reserved_keywords_report
	python manage.py check_reserved_keywords --report_path reserved_keywords_report --override_file db_keyword_overrides.yml

validate: test quality pii_check check_keywords ## run tests, quality, and PII annotation checks

migrate: ## apply database migrations
	python manage.py migrate

html_coverage: ## generate and view HTML coverage report
	coverage html && open htmlcov/index.html

# Define PIP_COMPILE_OPTS=-v to get more information during make upgrade.
PIP_COMPILE = pip-compile --upgrade $(PIP_COMPILE_OPTS)

define COMMON_CONSTRAINTS_TEMP_COMMENT
# This is a temporary solution to override the real common_constraints.txt\n# In edx-lint, until the pyjwt constraint in edx-lint has been removed.\n# See BOM-2721 for more details.\n# Below is the copied and edited version of common_constraints\n
endef

COMMON_CONSTRAINTS_TXT=requirements/common_constraints.txt
.PHONY: $(COMMON_CONSTRAINTS_TXT)
$(COMMON_CONSTRAINTS_TXT):
	wget -O "$(@)" https://raw.githubusercontent.com/edx/edx-lint/master/edx_lint/files/common_constraints.txt || touch "$(@)"
	echo "$(COMMON_CONSTRAINTS_TEMP_COMMENT)" | cat - $(@) > temp && mv temp $(@)

upgrade: export CUSTOM_COMPILE_COMMAND=make upgrade
upgrade: $(COMMON_CONSTRAINTS_TXT) ## update the requirements/*.txt files with the latest packages satisfying requirements/*.in
	sed 's/Django<4.0//g' requirements/common_constraints.txt > tmp_con; cat tmp_con > requirements/common_constraints.txt; rm tmp_con
	sed 's/django-simple-history==//g' requirements/common_constraints.txt > tmp_con; cat tmp_con > requirements/common_constraints.txt; rm tmp_con
	pip install -qr requirements/pip-tools.txt
	# Make sure to compile files after any other files they include!
	$(PIP_COMPILE) --allow-unsafe -o requirements/pip.txt requirements/pip.in
	$(PIP_COMPILE) -o requirements/pip-tools.txt requirements/pip-tools.in
	pip install -qr requirements/pip.txt
	pip install -qr requirements/pip-tools.txt
	$(PIP_COMPILE) -o requirements/base.txt requirements/base.in
	$(PIP_COMPILE) -o requirements/test.txt requirements/test.in
	$(PIP_COMPILE) -o requirements/doc.txt requirements/doc.in
	$(PIP_COMPILE) -o requirements/quality.txt requirements/quality.in
	$(PIP_COMPILE) -o requirements/validation.txt requirements/validation.in
	$(PIP_COMPILE) -o requirements/ci.txt requirements/ci.in
	$(PIP_COMPILE) -o requirements/dev.txt requirements/dev.in
	$(PIP_COMPILE) -o requirements/production.txt requirements/production.in

extract_translations: ## extract strings to be translated, outputting .mo files
	python manage.py makemessages -l en -v1 -d django
	python manage.py makemessages -l en -v1 -d djangojs

dummy_translations: ## generate dummy translation (.po) files
	cd enterprise_subsidy && i18n_tool dummy

compile_translations: # compile translation files, outputting .po files for each supported language
	python manage.py compilemessages

fake_translations: ## generate and compile dummy translation files

pull_translations: ## pull translations from Transifex
	tx pull -af -t --mode reviewed

push_translations: ## push source translation files (.po) from Transifex
	tx push -s

start-devstack: ## run a local development copy of the server
	docker-compose --x-networking up

open-devstack: ## open a shell on the server started by start-devstack
	docker exec -it enterprise-subsidy /edx/app/enterprise-subsidy/devstack.sh open

pkg-devstack: ## build the enterprise-subsidy image from the latest configuration and code
	docker build -t enterprise-subsidy:latest -f docker/build/enterprise-subsidy/Dockerfile git://github.com/openedx/configuration

detect_changed_source_translations: ## check if translation files are up-to-date
	cd enterprise_subsidy && i18n_tool changed

validate_translations: fake_translations detect_changed_source_translations ## install fake translations and check if translation files are up-to-date

# devstack-themed shortcuts
dev.up: dev.up.redis
	docker-compose up -d

dev.up.build: dev.up.redis
	docker-compose up -d --build

dev.up.build-no-cache: dev.up.redis
	docker-compose build --no-cache
	docker-compose up -d

dev.up.with-events: dev.up.kafka-control-center dev.up

dev.up.redis: # This has the nice side effect of starting the devstack_default network
	docker-compose -f $(DEVSTACK_WORKSPACE)/devstack/docker-compose.yml up -d redis

# Start kafka via the devstack docker-compose.yml
# https://github.com/openedx-unsupported/devstack/blob/323b475b885a2704489566b262e2895a4dca62b6/docker-compose.yml#L140
dev.up.kafka-control-center:
	docker-compose -f $(DEVSTACK_WORKSPACE)/devstack/docker-compose.yml up -d kafka-control-center

# Useful for just restarting everything related to the event broker
dev.down.kafka-control-center:
	docker-compose -f $(DEVSTACK_WORKSPACE)/devstack/docker-compose.yml down kafka zookeeper schema-registry kafka-control-center

dev.down: # Kills containers and all of their data that isn't in volumes
	docker-compose down

dev.stop: # Stops containers so they can be restarted
	docker-compose stop

app-shell: # Run the app shell as root
	docker exec -u 0 -it enterprise-subsidy.app bash

db-shell-57: # Run the mysql 5.7 shell as root, enter the app's database
	docker exec -u 0 -it enterprise-subsidy.db mysql -u root enterprise_subsidy

db-shell-8: # Run the mysql 8 shell as root, enter the app's database
	docker exec -u 0 -it enterprise-subsidy.mysql80 mysql -u root enterprise_subsidy

dev.backup:
	docker-compose stop app
	docker-compose up -d mysql80
	sleep 10 # let mysql process get fully warmed up
	docker compose exec mysql80 mysqldump --all-databases > .dev/enterprise_subsidy_all.sql

dev.restore:
	docker-compose stop app
	docker-compose up -d mysql80
	sleep 10 # let mysql process get fully warmed up
	docker compose exec -T mysql80 mysql < .dev/enterprise_subsidy_all.sql

dev.dbcopy8: ## Copy data from old mysql 5.7 container into a new 8 db
	mkdir -p .dev/
	docker-compose exec db bash -c "mysqldump --databases enterprise_subsidy" > .dev/enterprise_subsidy.sql
	docker-compose exec -T mysql80 bash -c "mysql" < .dev/enterprise_subsidy.sql
	rm .dev/enterprise_subsidy.sql

dev.static:
	docker-compose exec -u 0 app python3 manage.py collectstatic --noinput

dev.migrate:
	docker-compose exec -u 0 app python manage.py migrate

%-logs: # View the logs of the specified service container
	docker-compose logs -f --tail=500 $*

%-restart: # Restart the specified service container
	docker-compose restart $*

app-restart-devserver:  # restart just the app Django dev server
	docker-compose exec app bash -c 'kill $$(ps aux | egrep "manage.py ?\w* runserver" | egrep -v "while|grep" | awk "{print \$$2}")'

%-attach:
	docker attach enterprise-subsidy.$*

github_docker_auth:
	echo "$$DOCKERHUB_PASSWORD" | docker login -u "$$DOCKERHUB_USERNAME" --password-stdin

selfcheck: ## check that the Makefile is well-formed
	@echo "The Makefile is well-formed."

install_transifex_client: ## Install the Transifex client
	# Instaling client will skip CHANGELOG and LICENSE files from git changes
	# so remind the user to commit the change first before installing client.
	git diff -s --exit-code HEAD || { echo "Please commit changes first."; exit 1; }
	curl -o- https://raw.githubusercontent.com/transifex/cli/master/install.sh | bash
	git checkout -- LICENSE README.md ## overwritten by Transifex installer
