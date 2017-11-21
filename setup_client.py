#!/usr/bin/python

import sys

from landscape import UPSTREAM_VERSION


NAME = "Landscape Client"
DESCRIPTION = "Landscape Client"
PACKAGES = [
        "landscape.client",
        "landscape.client.broker",
        "landscape.client.manager",
        "landscape.client.monitor",
        "landscape.client.package",
        "landscape.client.upgraders",
        "landscape.client.user",
        ]
MODULES = [
        "landscape.client.accumulate",
        "landscape.client.amp",
        "landscape.client.configuration",
        "landscape.client.deployment",
        "landscape.client.diff",
        "landscape.client.patch",
        "landscape.client.reactor",
        "landscape.client.service",
        "landscape.client.sysvconfig",
        "landscape.client.watchdog",
        ]
SCRIPTS = []
if sys.version_info[0] > 2:
    SCRIPTS += [
        "scripts/landscape-client",
        "scripts/landscape-config",
        "scripts/landscape-broker",
        "scripts/landscape-manager",
        "scripts/landscape-monitor",
        "scripts/landscape-package-changer",
        "scripts/landscape-package-reporter",
        "scripts/landscape-release-upgrader",
        ]

# Dependencies

DEB_REQUIRES = [
        "ca-certificates",
        #python3-pycurl
        ]
REQUIRES = [
        "pycurl",
        "landscape-lib={}".format(UPSTREAM_VERSION),
        "landscape-sysinfo={}".format(UPSTREAM_VERSION),
        ]


if __name__ == "__main__":
    from setup import setup_landscape
    setup_landscape(
        name=NAME,
        description=DESCRIPTION,
        packages=PACKAGES,
        modules=MODULES,
        scripts=SCRIPTS,
        )
