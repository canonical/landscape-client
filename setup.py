#!/usr/bin/python
import setup_client
import setup_lib
import setup_sysinfo
from setup_common import setup_landscape

PACKAGES = []
MODULES = []
SCRIPTS = []
DEB_REQUIRES = []
REQUIRES = []
for sub in (setup_lib, setup_sysinfo, setup_client):
    PACKAGES += sub.PACKAGES
    MODULES += sub.MODULES
    SCRIPTS += sub.SCRIPTS
    DEB_REQUIRES += sub.DEB_REQUIRES
    REQUIRES += sub.REQUIRES


if __name__ == "__main__":
    setup_landscape(
        name="landscape-client",
        description="Landscape Client",
        packages=PACKAGES,
        modules=MODULES,
        scripts=SCRIPTS,
    )
