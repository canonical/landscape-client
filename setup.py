#!/usr/bin/python

from distutils.core import setup
import sys

from landscape import UPSTREAM_VERSION

from DistUtilsExtra.command import build_extra
from DistUtilsExtra.auto import clean_build_tree


SCRIPTS = []
if sys.version_info[0] == 3:
    SCRIPTS = [
            "scripts/landscape-client",
            "scripts/landscape-config",
            "scripts/landscape-broker",
            "scripts/landscape-manager",
            "scripts/landscape-monitor",
            "scripts/landscape-package-changer",
            "scripts/landscape-package-reporter",
            "scripts/landscape-release-upgrader",
            "scripts/landscape-sysinfo",
            ]


setup(name="Landscape Client",
      version=UPSTREAM_VERSION,
      description="Landscape Client",
      author="Landscape Team",
      author_email="landscape-team@canonical.com",
      url="http://landscape.canonical.com",
      packages=["landscape",
                "landscape.client",
                "landscape.client.broker",
                "landscape.client.manager",
                "landscape.client.monitor",
                "landscape.client.package",
                "landscape.client.upgraders",
                "landscape.client.user",
                "landscape.lib",
                "landscape.message_schemas",
                "landscape.sysinfo",
                ],
      scripts=SCRIPTS,
      cmdclass={"build": build_extra.build_extra,
                "clean": clean_build_tree})
