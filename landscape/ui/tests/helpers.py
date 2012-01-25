import dbus

from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.model.configuration.mechanism import (
    INTERFACE_NAME, ConfigurationMechanism)
from landscape.ui.model.configuration.proxy import ConfigurationProxy


class ConfigurationProxyHelper(object):
    """
    L{ConfigurationProxyHelper} will provide it's test case with a
    L{ConfigurationProxy} setup in such a way that it uses a real
    L{ConfigurationMechanism} (which in turn uses a real
    L{LandscapeSetupConfiguration}) but which does not make use of DBus for
    communication.

    Tests utilising this helper must define a L{test_case.config_string} for
    use in L{set_up} below.
    """

    def set_up(self, test_case):
        test_case.config_filename = test_case.makeFile(test_case.config_string)
        test_case.config = LandscapeSetupConfiguration()
        test_case.config.default_config_filenames = [test_case.config_filename]

        # We have to do these steps because the ConfigurationMechanism inherits
        # from dbus.service.Object which throws a fit if it notices you using
        # it without a mainloop.
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        try:
            bus = dbus.SessionBus(private=True)
        except dbus.exception.DBusError:
            test_case.skip = "Cannot launch private DBus session without X11"
            return
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
        test_case.mechanism = ConfigurationMechanism(test_case.config,
                                                     bus_name)

        test_case.proxy = ConfigurationProxy(interface=test_case.mechanism)
        test_case.proxy.load(["-c", test_case.config_filename])

    def tear_down(self, test_case):
        test_case.mechanism.remove_from_connection()
