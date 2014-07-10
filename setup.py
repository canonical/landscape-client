#!/usr/bin/python

from distutils.core import setup

from landscape import UPSTREAM_VERSION

from DistUtilsExtra.command import build_extra, build_i18n
from DistUtilsExtra.auto import clean_build_tree

# This is just because the path is hard to line-break.
glib_path = [
    "glib-2.0/schemas/com.canonical.landscape-client-settings.gschema.xml"]

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
                "landscape.lib",
                "landscape.ui",
                "landscape.ui.lib",
                "landscape.ui.model",
                "landscape.ui.model.configuration",
                "landscape.ui.model.registration",
                "landscape.ui.controller",
                "landscape.ui.view"],
      package_data={"landscape.ui.view": [
          "ui/landscape-client-settings.glade"]},
      data_files=[
          ("/usr/share/dbus-1/system-services/",
           ["dbus-1/com.canonical.LandscapeClientSettings.service",
            "dbus-1/com.canonical.LandscapeClientRegistration.service"]),
          ("/etc/dbus-1/system.d/",
           ["dbus-1/com.canonical.LandscapeClientSettings.conf",
            "dbus-1/com.canonical.LandscapeClientRegistration.conf",
            "dbus-1/landscape.conf"]),
          ("/usr/share/icons/hicolor/scalable/apps/",
           ["icons/preferences-management-service.svg"]),
          ("/usr/share/glib-2.0/schemas/", glib_path)],
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
               "scripts/landscape-dbus-proxy",
               "scripts/landscape-client-settings-mechanism",
               "scripts/landscape-client-registration-mechanism",
               "scripts/landscape-client-settings-ui",
               "scripts/landscape-client-ui-install"],
      cmdclass={"build_i18n":  build_i18n.build_i18n,
                "build": build_extra.build_extra,
                "clean": clean_build_tree})
