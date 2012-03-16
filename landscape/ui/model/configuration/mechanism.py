import sys

import dbus
import dbus.service

from landscape.ui.lib.polkit import PolicyKitMechanism, POLICY_NAME


SERVICE_NAME = "com.canonical.LandscapeClientSettings"
INTERFACE_NAME = "com.canonical.LandscapeClientSettings.ConfigurationInterface"
OBJECT_PATH = "/com/canonical/LandscapeClientSettings/ConfigurationInterface"


class PermissionDeniedByPolicy(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.LandscapeClientSettings.PermissionDeniedByPolicy"


class ConfigurationMechanism(PolicyKitMechanism):
    """
    L{ConfigurationMechanism} provides access to the
    L{LandscapeSetupConfiguration} object via DBus with access control
    implemented via PolicyKit policy.  The use of DBus results from the use of
    PolicyKit, not the other way around, and is done that way because that is
    considered to be the Right Thing for Ubuntu Desktop circa January 2012.
    """

    def __init__(self, config, bus_name, bypass=False, conn=None):
        super(ConfigurationMechanism, self).__init__(
            OBJECT_PATH, bus_name, PermissionDeniedByPolicy,
            bypass=bypass, conn=conn)
        self._config = config

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="as",
                         out_signature="",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def load(self, arglist, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            if len(arglist) > 0:
                self._config.load(arglist.split(chr(0x1e)))
            else:
                self._config.load([])
        return

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def reload(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self._config.reload()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="",
                         sender_keyword="sender", connection_keyword="conn")
    def write(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            self._config.write()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="",
                         out_signature="s",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def get_config_filename(self, sender=None, conn=None):
        return self._config.get_config_filename()

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s",
                         out_signature="s",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def get(self, name, sender=None, conn=None):
        """
        Return the configuration option value associated with L{name} from the
        L{LandscapeSetupConfiguration}.
        """
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            try:
                value = self._config.get(name)
            except AttributeError:
                return ""
            if value is None:
                return ""
            return str(value)
        return ""

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="ss",
                         out_signature="",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def set(self, name, value, sender=None, conn=None):
        """
        Set the configuration option associated with L{name} to L{value} in the
        L{LandscapeSetupConfiguration}.
        """
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            # Underlying _config does not support unicode so convert to ascii
            value = unicode(value).encode("ascii", errors="replace")
            setattr(self._config, name, value)

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="",
                         out_signature="",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def exit(self, sender=None, conn=None):
        """
        Exit this process.
        """
        sys.exit(0)
