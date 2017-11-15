#!/usr/bin/python

from distutils.core import setup

# from python3-distutils-extra
from DistUtilsExtra.command import build_extra
from DistUtilsExtra.auto import clean_build_tree

from landscape import UPSTREAM_VERSION


SETUP = dict(
        name=None,
        description=None,
        packages=None,
        py_modules=None,
        scripts=None,

        version=UPSTREAM_VERSION,
        author="Landscape Team",
        author_email="landscape-team@canonical.com",
        url="http://landscape.canonical.com",
        cmdclass={"build": build_extra.build_extra,
                  "clean": clean_build_tree},
        )


def setup_landscape(name, description, packages, modules=None, scripts=None,
                    **kwargs):
    assert name and description and packages
    kwargs = dict(SETUP,
                  name=name,
                  description=description,
                  packages=packages,
                  py_modules=modules,
                  scripts=scripts,
                  **kwargs)
    kwargs = {k: v for k, v in kwargs.items() if k is not None}
    setup(**kwargs)


# Import these afterward to avoid circular imports.
import setup_lib, setup_sysinfo, setup_client

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
