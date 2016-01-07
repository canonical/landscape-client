#!/usr/bin/python

from distutils.core import setup

from landscape import UPSTREAM_VERSION

from DistUtilsExtra.command import build_extra
from DistUtilsExtra.auto import clean_build_tree

setup(name="Landscape Client",
      version=UPSTREAM_VERSION,
      description="Landscape Client",
      author="Landscape Team",
      author_email="landscape-team@canonical.com",
      url="http://landscape.canonical.com",
      packages=["landscape",
                "landscape.broker",
                "landscape.manager",
                "landscape.monitor",
                "landscape.package",
                "landscape.sysinfo",
                "landscape.upgraders",
                "landscape.user",
                "landscape.lib"],
      data_files=[
          ("/etc/dbus-1/system.d/", ["dbus-1/landscape.conf"])],
      scripts=["scripts/landscape-client",
               "scripts/landscape-config",
               "scripts/landscape-message",
               "scripts/landscape-broker",
               "scripts/landscape-manager",
               "scripts/landscape-monitor",
               "scripts/landscape-package-changer",
               "scripts/landscape-package-reporter",
               "scripts/landscape-release-upgrader",
               "scripts/landscape-sysinfo",
               "scripts/landscape-dbus-proxy"],
      cmdclass={"build": build_extra.build_extra,
                "clean": clean_build_tree})
