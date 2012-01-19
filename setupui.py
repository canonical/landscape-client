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
        install_bin = self.get_finalized_command('install_scripts')
        script_install_dir = install_bin.install_dir
        output = ""
        service_dir = "/usr/share/dbus-1/system-services/"
        for service_file in os.listdir(service_dir):
            if service_file.find("com.canonical.LandscapeClient") > -1:
                service_path = os.path.join(service_dir, service_file)
                ff = open(service_path, "r")
                output = ""
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
                "landscape.ui.lib",
                "landscape.ui.model",
                "landscape.ui.model.configuration",
                "landscape.ui.model.registration",
                "landscape.ui.controller",
                "landscape.ui.view"],
      package_data={"landscape.ui.view":
                        ["ui/landscape-client-settings.glade"]},
      data_files=[
        ('/usr/share/dbus-1/system-services/',
         ['polkit-1/com.canonical.LandscapeClientSettings.service',
          'polkit-1/com.canonical.LandscapeClientRegistration.service']),
        ('/usr/share/polkit-1/actions',
         ['polkit-1/com.canonical.LandscapeClientSettings.policy',
          'polkit-1/com.canonical.LandscapeClientRegistration.policy']),
        ('/etc/dbus-1/system.d/',
         ['polkit-1/com.canonical.LandscapeClientSettings.conf',
          'polkit-1/com.canonical.LandscapeClientRegistration.conf'])],
      scripts=['scripts/landscape-client-settings-mechanism',
               'scripts/landscape-client-registration-mechanism',
               "scripts/landscape-client-settings-ui"],
      cmdclass={"install_dbus_service": install_dbus_service})
