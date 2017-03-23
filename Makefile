PYDOCTOR ?= pydoctor
TXT2MAN ?= txt2man
PYTHON ?= python
TRIAL_ARGS ?=
TEST_COMMAND_PY2 = trial --unclean-warnings $(TRIAL_ARGS) landscape
TEST_COMMAND_PY3 = trial3 --unclean-warnings $(TRIAL_ARGS) landscape
READY_FILE := py3_ready_tests
PY3_READY := `cat $(READY_FILE)`
TEST_COMMAND_PY3_READY = TRIAL_ARGS= trial3 --unclean-warnings $(PY3_READY)
UBUNTU_RELEASE := $(shell lsb_release -cs)
# version in the code is authoritative
# Use := here, not =, it's really important, otherwise UPSTREAM_VERSION
# will be updated behind your back with the current result of that
# command everytime it is mentioned/used.
UPSTREAM_VERSION := $(shell python -c "from landscape import UPSTREAM_VERSION; print UPSTREAM_VERSION")
CHANGELOG_VERSION := $(shell dpkg-parsechangelog | grep ^Version | cut -f 2 -d " " | cut -f 1 -d '-')
BZR_REVNO := $(shell bzr revno)
ifeq (+bzr,$(findstring +bzr,$(UPSTREAM_VERSION)))
TARBALL_VERSION := $(UPSTREAM_VERSION)
else
TARBALL_VERSION := $(UPSTREAM_VERSION)+bzr$(BZR_REVNO)
endif

.PHONY: help
help:  ## Print help about available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: depends
depends: depends2 depends3  ## Install py2 and py3 dependencies.

.PHONY: depends2
depends2:
	sudo apt -y install python-twisted-core python-distutils-extra python-mock python-configobj python-passlib

.PHONY: depends3
depends3:
	sudo apt -y install python3-twisted python3-distutils-extra python3-mock python3-configobj python3-passlib

all: build

.PHONY: build
build: build2 build3   ## Build.

.PHONY: build2
build2:
	$(PYTHON) setup.py build_ext -i

.PHONY: build3
build3:
	python3 setup.py build_ext -i

.PHONY: check5
check5:
	-trial --unclean-warnings --reporter=summary landscape > _last_py2_res
	-trial3 --unclean-warnings landscape
	./display_py2_testresults

.PHONY: check
check: check2 check3-ready  ## Run all the tests.

.PHONY: check2
check2: build
	LC_ALL=C $(TEST_COMMAND_PY2)

.PHONY: check3
check3: build3
	LC_ALL=C $(TEST_COMMAND_PY3)

.PHONY: check3-ready
check3-ready:  ## Run py3 tests for ported modules (listed in py3_ready_tests).
	LC_ALL=C $(TEST_COMMAND_PY3_READY)

.PHONY: ci-check
ci-check: depends build check  ## Install dependencies and run all the tests.

.PHONY: lint
lint:
	bzr ls-lint

.PHONY: pyflakes
pyflakes:
	-pyflakes `find landscape -name \*py`

clean:
	-find landscape -name \*.pyc -exec rm -f {} \;
	-rm tags
	-rm _trial_temp -rf
	-rm docs/api -rf;
	-rm man/\*.1 -rf
	-rm sdist -rf

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

origtarball: sdist
	cp -f sdist/landscape-client-$(TARBALL_VERSION).tar.gz \
		../landscape-client_$(TARBALL_VERSION).orig.tar.gz

prepchangelog:
# add a temporary entry for a local build if needed
ifeq (,$(findstring +bzr,$(CHANGELOG_VERSION)))
	dch -v $(TARBALL_VERSION)-0ubuntu0 "New local test build" --distribution $(UBUNTU_RELEASE)
else
# just update the timestamp
	dch --distribution $(UBUNTU_RELEASE) --release $(UBUNTU_RELEASE)
endif

updateversion:
	sed -i -e "s/^UPSTREAM_VERSION.*/UPSTREAM_VERSION = \"$(TARBALL_VERSION)\"/g" \
		landscape/__init__.py

package: clean prepchangelog updateversion
	debuild -b $(DEBUILD_OPTS)

sourcepackage: clean origtarball prepchangelog updateversion
	# need to remove sdist here because it doesn't exist in the
	# orig tarball
	rm -rf sdist
	debuild -S $(DEBUILD_OPTS)

MESSAGE_DIR = `pwd`/runclient-messages
LOG_FILE = `pwd`/runclient.log

freshdata:
	-sudo rm -rf $(MESSAGE_DIR)
	-sudo mkdir $(MESSAGE_DIR)

run:
	-sudo ./landscape-client \
		-a onward -t "John's PC" \
		-u http://localhost:8080/message-system \
		-d $(MESSAGE_DIR) \
		--urgent-exchange-interval=5 \
		--log-level=debug \
		--ping-url=http://localhost:8081/ping \

freshrun: freshdata run

tags:
	-ctags --languages=python -R .

etags:
	-etags --languages=python -R .

releasetarball:
	make sdist TARBALL_VERSION=$(UPSTREAM_VERSION)

sdist: clean
	mkdir -p sdist
	# --uncommitted because we want any changes the developer might have made
	# locally to be included in the package without having to commit
	bzr export --uncommitted sdist/landscape-client-$(TARBALL_VERSION)
	rm -rf sdist/landscape-client-$(TARBALL_VERSION)/debian
	sed -i -e "s/^UPSTREAM_VERSION.*/UPSTREAM_VERSION = \"$(TARBALL_VERSION)\"/g" \
		sdist/landscape-client-$(TARBALL_VERSION)/landscape/__init__.py
	cd sdist && tar cfz landscape-client-$(TARBALL_VERSION).tar.gz landscape-client-$(TARBALL_VERSION)
	cd sdist && md5sum landscape-client-$(TARBALL_VERSION).tar.gz > landscape-client-$(TARBALL_VERSION).tar.gz.md5
	rm -rf sdist/landscape-client-$(TARBALL_VERSION)

.PHONY: tags etags freshdata run freshrun package sourcepackage updateversion origtarball prepchangelog lint releasetarball
.DEFAULT_GOAL := help
