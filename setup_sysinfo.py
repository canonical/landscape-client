#!/usr/bin/python
from landscape import UPSTREAM_VERSION

NAME = "Landscape Sysinfo"
DESCRIPTION = "Landscape Client"
PACKAGES = ["landscape.sysinfo"]
MODULES = []
SCRIPTS = ["scripts/landscape-sysinfo"]

# Dependencies
DEB_REQUIRES = []
REQUIRES = [f"landscape-lib={UPSTREAM_VERSION}"]


if __name__ == "__main__":
    from setup_common import setup_landscape

    setup_landscape(
        name=NAME,
        description=DESCRIPTION,
        packages=PACKAGES,
        modules=MODULES,
        scripts=SCRIPTS,
    )
