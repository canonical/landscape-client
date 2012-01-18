#!/usr/bin/python

import os

from distutils.core import setup, Command
from distutils.command.install import install

from landscape import UPSTREAM_VERSION


class install_dbus_service(Command):
    description = "Fix script path in DBus service config"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        print "Bingo bob"
        install_bin = self.get_finalized_command('install_scripts')
        script_install_dir = install_bin.install_dir
        output = ""
        service_dir = "/usr/share/dbus-1/system-services/"
        service_file = "com.canonical.LandscapeClientSettings.service"
        service_path = os.path.join(service_dir, service_file)
        ff = open(service_path, "r")
        for line in ff.readlines():
            if line.strip()[:5] == "Exec=":
                line = line.replace("/usr/bin", script_install_dir)
            output += line
        ff.close()
        ff = open(service_path, "w")
        ff.write(output)
        ff.close()


pkit_description = \
    "PolicyKit mechanism and policy for Landscape Client settings."
author = "Landscape Team"
author_email = "landscape-team@canonical.com"
url = "http://landscape.canonical.com"

install.sub_commands.append(('install_dbus_service', None))
setup(name="landscape Client Settings PolicyKit",
      version=UPSTREAM_VERSION,
      description=pkit_description,
      author=author,
      author_email=author_email,
      url=url,
      packages=["landscape.ui",
                "landscape.ui.model",
                "landscape.ui.model.configuration",
                "landscape.ui.controller",
                "landscape.ui.view"],
      package_data={"landscape.ui.view":
                        ["ui/landscape-client-settings.glade"]},
      data_files=[
        ('/usr/share/dbus-1/system-services/',
         ['polkit-1/com.canonical.LandscapeClientSettings.service']),
        ('/usr/share/polkit-1/actions',
         ['polkit-1/com.canonical.LandscapeClientSettings.policy']),
        ('/etc/dbus-1/system.d/',
         ['polkit-1/com.canonical.LandscapeClientSettings.conf'])],
      scripts=['scripts/landscape-client-settings-mechanism',
               "scripts/landscape-client-settings-ui"],
      cmdclass={"install_dbus_service": install_dbus_service})
