#!/usr/bin/python
import os
import shutil
import glob
from setuptools import setup, Command

from landscape import UPSTREAM_VERSION

# Custom clean command to replace the one from DistUtilsExtra
class CleanCommand(Command):
    user_options = []

    def run(self):

        for pattern in ['build', 'dist', '.eggs', '*.egg-info']:
            for path in glob.glob(pattern):
                if os.path.isdir(path):
                    shutil.rmtree(path)

        # Recursively remove __pycache__ and compiled files
        for root, dirs, files in os.walk('.'):
            if '__pycache__' in dirs:
                path = os.path.join(root, '__pycache__')
                shutil.rmtree(path)
                dirs.remove('__pycache__')  

            for file in files:
                if file.endswith(('.pyc', '.pyo')):
                    path = os.path.join(root, file)
                    os.remove(path)


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
    cmdclass={"clean": CleanCommand},
)


def setup_landscape(
    name,
    description,
    packages,
    modules=None,
    scripts=None,
    **kwargs,
):
    
    assert name and description and packages
    kwargs = dict(
        SETUP,
        name=name,
        description=description,
        packages=packages,
        py_modules=modules,
        scripts=scripts,
        **kwargs,
    )

    kwargs = {k: v for k, v in kwargs.items() if k is not None}
    setup(**kwargs)


# Import these afterward to avoid circular imports.
import setup_lib  # noqa: E402
import setup_sysinfo  # noqa: E402
import setup_client  # noqa: E402

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