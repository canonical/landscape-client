#!/usr/bin/python

from distutils.core import setup, Extension

from landscape import UPSTREAM_VERSION


setup(name="Landscape Client",
      version=UPSTREAM_VERSION,
      description="Landscape Client",
      author="Landscape Team",
      author_email="landscape-team@canonical.com",
      urk="http://landscape.canonical.com",
      packages=["landscape",
                "landscape.broker",
                "landscape.manager",
                "landscape.monitor",
                "landscape.package",
                "landscape.sysinfo",
                "landscape.upgraders",
                "landscape.user",
                "landscape.lib"],
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
               "scripts/landscape-is-cloud-managed"],
      ext_modules=[Extension("landscape.lib.initgroups",
                             ["landscape/lib/initgroups.c"])]
          )
