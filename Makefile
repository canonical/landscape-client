PYDOCTOR ?= pydoctor
TXT2MAN ?= txt2man
PYTHON ?= python3
SNAPCRAFT = SNAPCRAFT_BUILD_INFO=1 snapcraft
TRIAL ?= -m landscape.lib.run_tests
TRIAL_ARGS ?=


.PHONY: help
help:  ## Print help about available targets
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends:
	sudo apt update && sudo apt-get -y install python3-configobj python3-coverage \
		python3-mock python3-netifaces python3-pip python3-pycurl python3-twisted\
		net-tools

.PHONY: depends-dev
depends-dev: depends
	pip install jinja2-cli ruff coverage[toml]

# -common seems a catch-22, but this is just a shortcut to
# initialize user and dirs, some used through tests.
.PHONY: depends-ci
depends-ci: depends
	sudo apt-get -y install landscape-common python3-pytest

all: build

.PHONY: build
build:
	$(PYTHON) setup.py build_ext -i

# trial3 does not support threading via `-j` at the moment
# so we ignore TRIAL_ARGS.
# TODO: Respect $TRIAL_ARGS once trial3 is fixed.
.PHONY: check
check: TRIAL_ARGS=
check: build 
	@if ! echo "$$DEB_BUILD_OPTIONS" | grep -qw nocheck; then \
		PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON) $(TRIAL) --unclean-warnings $(TRIAL_ARGS) landscape; \
	fi

.PHONY: coverage
coverage:
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON) -m coverage run $(TRIAL) --unclean-warnings landscape
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON) -m coverage xml

.PHONY: ruff-fix
ruff-fix:
	ruff check --fix
	ruff format

.PHONY: ruff-check
ruff-check:
	ruff check
	ruff format --check

.PHONY: lint 
lint: ruff-fix

.PHONY: clean
clean:
	-find landscape -name __pycache__ -exec rm -rf {} \;
	-find landscape -name \*.pyc -exec rm -f {} \;
	-rm -rf .coverage
	-rm -rf coverage
	-rm -rf tags
	-rm -rf _trial_temp
	-rm -rf docs/api
	-rm -rf man/\*.1
	-rm -rf sdist

doc: docs/api/twisted/pickle
	mkdir -p docs/api
	${PYDOCTOR} --make-html --html-output docs/api --add-package landscape --extra-system=docs/api/twisted/pickle:twisted/

docs/api/twisted/pickle:
	mkdir -p docs/api/twisted
	-${PYDOCTOR} --make-html --html-output docs/api/twisted --add-package /usr/share/pyshared/twisted -o docs/api/twisted/pickle

manpages:
	LC_ALL=C ${TXT2MAN} -P Landscape -s 1 -t landscape-client < man/landscape-client.txt > man/landscape-client.1
	LC_ALL=C ${TXT2MAN} -P Landscape -s 1 -t landscape-config < man/landscape-config.txt > man/landscape-config.1
	LC_ALL=C ${TXT2MAN} -P Landscape -s 1 -t landscape-sysinfo < man/landscape-sysinfo.txt > man/landscape-sysinfo.1

MESSAGE_DIR = `pwd`/runclient-messages
LOG_FILE = `pwd`/runclient.log

.PHONY: freshdata
freshdata:
	-sudo rm -rf $(MESSAGE_DIR)
	-sudo mkdir $(MESSAGE_DIR)

.PHONY: run
run:
	-sudo ./landscape-client \
		-a onward -t "John's PC" \
		-u http://localhost:8080/message-system \
		-d $(MESSAGE_DIR) \
		--urgent-exchange-interval=5 \
		--log-level=debug \
		--ping-url=http://localhost:8081/ping \

.PHONY: freshrun
freshrun: freshdata run

.PHONY: tags
tags:
	-ctags --languages=python -R .

.PHONY: etags
etags:
	-etags --languages=python -R .

.PHONY: snap-yaml
snap-yaml:
	jinja2 snap/snapcraft.yaml.j2 -D base=core24 > snap/snapcraft.yaml

.PHONY: snap-install
snap-install:
	$(eval VERSION=$(shell yq ".version" snap/snapcraft.yaml))
	sudo snap install --devmode landscape-client_$(VERSION)_amd64.snap

.PHONY: snap-remote-build
snap-remote-build: snap-yaml
	snapcraft remote-build

.PHONY: snap-remove
snap-remove:
	sudo snap remove --purge landscape-client

.PHONY: snap-shell
snap-shell: snap-install
	sudo snap run --shell landscape-client.landscape-client

.PHONY: snap-debug
snap-debug: snap-yaml
	$(SNAPCRAFT) -v --debug

.PHONY: snap-clean
snap-clean: snap-remove
	$(eval VERSION=$(shell yq ".version" snap/snapcraft.yaml))
	$(SNAPCRAFT) clean
	-rm landscape-client_$(VERSION)_amd64.snap

.PHONY: snap
snap: snap-yaml
	$(SNAPCRAFT)

# TICS expects coverage info to be in ./coverage/.coverage
.PHONY: prepare-tics-analysis
prepare-tics-analysis: depends-ci coverage
	sudo apt install pylint
	mkdir -p coverage
	cp .coverage ./coverage/.coverage
	cp coverage.xml ./coverage/coverage.xml

include Makefile.packaging

.DEFAULT_GOAL := help
