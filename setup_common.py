import shutil
from pathlib import Path

from setuptools import Command, setup

from landscape import PYTHON_VERSION


class CleanCommand(Command):
    """
    Custom clean command to replace the one from DistUtilsExtra
    """

    user_options = []

    def run(self):
        for pattern in ["build", "dist", ".eggs", "*.egg-info"]:
            for path in Path(".").glob(pattern):
                if path.is_dir(path):
                    shutil.rmtree(path)

        # Recursively remove __pycache__ and compiled files
        for pycache in Path(".").rglob("__pycache__"):
            if pycache.is_dir():
                shutil.rmtree(pycache)
        for compiled in Path(".").rglob("*.py[co]"):
            if compiled.is_file():
                compiled.unlink()

    def initialize_options(self):
        self.all = True

    def finalize_options(self): ...


SETUP = dict(
    name=None,
    description=None,
    packages=None,
    py_modules=None,
    scripts=None,
    version=PYTHON_VERSION,
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
