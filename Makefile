PYDOCTOR ?= pydoctor
TXT2MAN ?= txt2man 
PYTHON ?= python
TRIAL_ARGS ?= 
TEST_COMMAND_PY2 = trial --unclean-warnings $(TRIAL_ARGS) landscape
TEST_COMMAND_PY3 = trial3 --unclean-warnings $(TRIAL_ARGS) landscape
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

all: build

build3:
	python3 setup.py build_ext -i

build:
	$(PYTHON) setup.py build_ext -i

check5:
	-trial --unclean-warnings --reporter=summary landscape > _last_py2_res
	-trial3 --unclean-warnings landscape
	./display_py2_testresults

check3: build3 
	@if [ -z "$$DBUS_SESSION_BUS_ADDRESS" ]; then \
		OUTPUT=`dbus-daemon --print-address=1 --print-pid=1 --session --fork`; \
		export DBUS_SESSION_BUS_ADDRESS=`echo $$OUTPUT | cut -f1 -d ' '`; \
		DBUS_PID=`echo $$OUTPUT | cut -f2 -d ' '`; \
		trap "kill $$DBUS_PID" EXIT; \
	fi; \
	if [ -z "$$DISPLAY" ]; then \
		xvfb-run $(TEST_COMMAND_PY3); \
	else \
	    $(TEST_COMMAND_PY3); \
	fi

check: build
	if [ -z "$$DISPLAY" ]; then \
		xvfb-run $(TEST_COMMAND_PY2); \
	else \
	    $(TEST_COMMAND_PY2); \
	fi

lint:
	bzr ls-lint

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

.PHONY: tags etags freshdata run freshrun package sourcepackage updateversion origtarball prepchangelog lint build check releasetarball
