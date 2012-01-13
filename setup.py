#!/usr/bin/python

from distutils.core import setup, Extension

from landscape import UPSTREAM_VERSION

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
                "landscape.ui",
                "landscape.ui.model",
                "landscape.ui.controller",
                "landscape.ui.view",
                "landscape.upgraders",
                "landscape.user",
                "landscape.lib"],
      package_data={"landscape.ui.view":
                        ["ui/landscape-client-settings.glade"]},
      scripts=["scripts/landscape-client",
               "scripts/landscape-client-settings-ui",
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
