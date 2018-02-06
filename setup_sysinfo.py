#!/usr/bin/python

import sys

from landscape import UPSTREAM_VERSION


NAME = "Landscape Sysinfo"
DESCRIPTION = "Landscape Client"
PACKAGES = [
        "landscape.sysinfo",
        ]
MODULES = []
SCRIPTS = []
if sys.version_info[0] > 2:
    SCRIPTS += [
        "scripts/landscape-sysinfo",
        ]

# Dependencies

DEB_REQUIRES = [
        ]
REQUIRES = [
        "landscape-lib={}".format(UPSTREAM_VERSION),
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
