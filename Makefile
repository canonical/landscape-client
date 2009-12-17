PYDOCTOR ?= pydoctor
TXT2MAN=man/txt2man
PYTHON ?= python

all: build

build:
	$(PYTHON) setup.py build_ext -i

check: build
	-./test
	-pyflakes landscape

checkcertificate:
	-echo | openssl s_client -connect landscape.canonical.com:443 -CAfile /etc/ssl/certs/ca-certificates.crt

clean:
	-find landscape -name \*.pyc -exec rm {} \;
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
	${TXT2MAN} -P Landscape -t landscape-client < man/landscape-client.txt > man/landscape-client.1
	${TXT2MAN} -P Landscape -t landscape-config < man/landscape-config.txt > man/landscape-config.1
	${TXT2MAN} -P Landscape -t landscape-message < man/landscape-message.txt > man/landscape-message.1

package: manpages
	@fakeroot debian/rules binary
	@echo "\n\nYou remembered to update the changelog, right?\n\n"

SSH_USERNAME=`whoami`
SSH_HOST=people.ubuntu.com
PACKAGE_DIR=/home/jkakar/public_html/landscape
deploy:
ifneq (${PACKAGE},)
	@echo "Copying ${PACKAGE} to $(SSH_HOST):$(PACKAGE_DIR)"
	@scp ${PACKAGE} $(SSH_USERNAME)@$(SSH_HOST):$(PACKAGE_DIR)
	@echo "\nScanning packages and recreating the Packages file."
	@ssh -l $(SSH_USERNAME) $(SSH_HOST) \
		"cd $(PACKAGE_DIR) " \
		"&& dpkg-scanpackages . /dev/null > Packages " \
		"&& gzip -f Packages"
else
	@echo "You need to specify PACKAGE, as in: make deploy PACKAGE=<name>"
endif

MESSAGE_DIR = `pwd`/runclient-messages
LOG_FILE = `pwd`/runclient.log

reinstall:
	-sudo dpkg -P landscape-client
	-sudo rm -rf /var/log/landscape /etc/landscape /var/lib/landscape /etc/default/landscape-client
	-sudo apt-get install landscape-client

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

UPSTREAM_VERSION=$(shell python -c "from landscape import UPSTREAM_VERSION; print UPSTREAM_VERSION")
sdist:
	mkdir -p sdist
	bzr export sdist/landscape-client-$(UPSTREAM_VERSION)
	rm -rf sdist/landscape-client-$(UPSTREAM_VERSION)/debian
	cd sdist && tar cfz landscape-client-$(UPSTREAM_VERSION).tar.gz landscape-client-$(UPSTREAM_VERSION)
	cd sdist && md5sum landscape-client-$(UPSTREAM_VERSION).tar.gz > landscape-client-$(UPSTREAM_VERSION).tar.gz.md5
	rm -rf sdist/landscape-client-$(UPSTREAM_VERSION)

.PHONY: tags etags
