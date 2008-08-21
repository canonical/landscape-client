#!/usr/bin/python

from distutils.core import setup

setup(name="Landscape Client",
      version="AUTOPPA_VERSION(1.0.17-feisty1-landscape1)"[len("AUTOPPA_VERSION("):-1],
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
      scripts=["scripts/landscape-client",
               "scripts/landscape-config",
               "scripts/landscape-message",
               "scripts/landscape-broker",
               "scripts/landscape-manager",
               "scripts/landscape-monitor",
               "scripts/landscape-package-changer",
               "scripts/landscape-package-reporter",
               "scripts/landscape-sysinfo"],
     )
