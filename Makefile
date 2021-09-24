PYDOCTOR ?= pydoctor
TXT2MAN ?= txt2man
PYTHON2 ?= python2
PYTHON3 ?= python3
TRIAL ?= -m twisted.trial
TRIAL_ARGS ?=

.PHONY: help
help:  ## Print help about available targets
	@grep -h -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends: depends3  ## py2 is deprecated
	sudo apt-get -y install python3-flake8 python3-coverage

.PHONY: depends2
depends2:
	sudo apt-get -y install python-twisted-core python-distutils-extra python-mock python-configobj python-netifaces python-pycurl

.PHONY: depends3
depends3:
	sudo apt-get -y install python3-twisted python3-distutils-extra python3-mock python3-configobj python3-netifaces python3-pycurl

all: build

.PHONY: build
build: build2 build3   ## Build.

.PHONY: build2
build2:
	$(PYTHON2) setup.py build_ext -i

.PHONY: build3
build3:
	$(PYTHON3) setup.py build_ext -i

.PHONY: check
check: check2 check3  ## Run all the tests.

.PHONY: check2
check2: build2
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON2) $(TRIAL) --unclean-warnings $(TRIAL_ARGS) landscape

# trial3 does not support threading via `-j` at the moment
# so we ignore TRIAL_ARGS.
# TODO: Respect $TRIAL_ARGS once trial3 is fixed.
.PHONY: check3
check3: TRIAL_ARGS=
check3: build3
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON3) $(TRIAL) --unclean-warnings $(TRIAL_ARGS) landscape

.PHONY: coverage
coverage:
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON3) -m coverage run $(TRIAL) --unclean-warnings landscape
	PYTHONPATH=$(PYTHONPATH):$(CURDIR) LC_ALL=C $(PYTHON3) -m coverage xml

.PHONY: lint
lint:
	$(PYTHON3) -m flake8 --ignore E24,E121,E123,E125,E126,E221,E226,E266,E704,E265,W504 \
		`find landscape -name \*.py`

.PHONY: pyflakes
pyflakes:
	-pyflakes `find landscape -name \*.py`

clean:
	-find landscape -name __pycache__ -exec rm -rf {} \;
	-find landscape -name \*.pyc -exec rm -f {} \;
	-rm -rf .coverage
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

include Makefile.packaging

.DEFAULT_GOAL := help
