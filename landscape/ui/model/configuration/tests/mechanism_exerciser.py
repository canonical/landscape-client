#!/usr/bin/env python

import os
import sys

import dbus

tests = os.path.abspath("./")
location = os.path.dirname(os.path.abspath(sys.argv[0]))
if tests.endswith("_trial_temp"):
    sys.path.insert(0, os.path.abspath(os.path.join(tests, "../")))
elif location == tests:
    sys.path.insert(0, os.path.abspath(os.path.join(tests, "../../../../../")))


from landscape.ui.model.configuration.mechanism import (
    ConfigurationMechanism, listen, INTERFACE_NAME)


class TestableConfigurationMechanism(ConfigurationMechanism):
    
    def __init__(self, bus_name):
        super(TestableConfigurationMechanism, self).__init__(None, bus_name)


if __name__ == "__main__":
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
    mechanism = TestableConfigurationMechanism(bus_name)
    listen()
