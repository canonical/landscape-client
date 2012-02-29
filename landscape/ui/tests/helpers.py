import os

from lxml import etree
import dbus
from gi.repository import Gdk

from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.model.configuration.mechanism import (
    INTERFACE_NAME, ConfigurationMechanism)
from landscape.ui.model.configuration.proxy import ConfigurationProxy


# We have to do these steps because the ConfigurationMechanism inherits
# from dbus.service.Object which throws a fit if it notices you using
# it without a mainloop.
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
dbus_test_should_skip = False
dbus_skip_message = "Cannot launch private DBus session without X11"
try:
    bus = dbus.SessionBus(private=True)
    bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
except dbus.exceptions.DBusException:
    bus = object
    bus_name = ""
    dbus_test_should_skip = True


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
        if not dbus_test_should_skip:
            test_case.config_filename = test_case.makeFile(
                test_case.config_string)
            test_case.config = LandscapeSetupConfiguration()
            test_case.config.default_config_filenames = \
                [test_case.config_filename]

            test_case.mechanism = ConfigurationMechanism(test_case.config,
                                                         bus_name)

            test_case.proxy = ConfigurationProxy(interface=test_case.mechanism)
            test_case.proxy.load(["-c", test_case.config_filename])

    def tear_down(self, test_case):
        if not dbus_test_should_skip:
            test_case.mechanism.remove_from_connection()


class FakeGSettings(object):
    """
    This class impersonates a real L{gi.repostiroy.Gio.GSettings}
    object to allow for testing code that utilises it without setting values in
    the live DConf.
    """

    calls = {}

    def __init__(self, data={}):
        self.set_data(data)
        tree = etree.parse(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../../../",
                "glib-2.0/schemas/",
                "com.canonical.landscape-client-settings.gschema.xml"))
        root = tree.getroot()
        self.schema = root.find("schema")
        assert(self.schema.attrib["id"] == \
                   "com.canonical.landscape-client-settings")
        self.keys = {}
        for key in self.schema.findall("key"):
            self.keys[key.attrib["name"]] = key.attrib["type"]

    def check_key_data(self, name, gstype):
        if name in self.keys:
            if self.keys[name] == gstype:
                return True
            else:
                raise ValueError("The GSchema file says %s is a %s, " +
                                 "but you asked for a %s" %
                                 (name, self.keys[name], gstype))
        else:
            raise KeyError("Can't find %s in the GSchema file!" % name)

    def get_value(self, name, gstype):
        if self.check_key_data(name, gstype):
            return self.data[name]

    def set_value(self, name, gstype, value):
        if self.check_key_data(name, gstype):
            self.data[name] = value

    def set_data(self, data):
        self.data = data

    def _call(self, name, *args):
        [count, arglist] = self.calls.get(name, (0, []))
        count += 1
        arglist.append(self._args_to_string(*args))
        self.calls[name] = [count, arglist]

    def _args_to_string(self, *args):
        return "|".join([str(arg) for arg in args])

    def new(self, key):
        self._call("new", key)
        return self

    def connect(self, signal, callback, *args):
        self._call("connect", signal, callback, *args)

    def get_boolean(self, name):
        self._call("get_boolean", name)
        return self.get_value(name, "b")

    def set_boolean(self, name, value):
        self._call("set_boolean", name, value)
        self.set_value(name, "b", value)

    def get_string(self, name):
        self._call("get_string", name)
        return self.get_value(name, "s")

    def set_string(self, name, value):
        self._call("set_string", name, value)
        self.set_value(name, "s", value)

    def was_called(self, name):
        return self.calls.haskey(name)

    def was_called_with_args(self, name, *args):
        try:
            [count, arglist] = self.calls.get(name, (0, []))
        except KeyError:
            return False

        expected_args = self._args_to_string(*args)
        return expected_args in arglist


def simulate_gtk_key_release(window, widget, key):
    keypress = Gdk.Event(Gdk.EventType.KEY_PRESS)
    keypress.keyval = key
    keypress.window = window
    keypress.send_event = True
    widget.emit("key-press-event", keypress)
    keypress = Gdk.Event(Gdk.EventType.KEY_RELEASE)
    keypress.keyval = key
    keypress.window = window
    keypress.send_event = True
    widget.emit("key-release-event", keypress)
