import dbus
import dbus.service
import dbus.mainloop.glib
import gobject

from landscape.configuration import LandscapeSetupConfiguration


SERVICE_NAME = "com.canonical.landscape_settings.configure"
INTERFACE_NAME = "com.canonical.landscape_settings.ConfigurationInterface"
OBJECT_PATH = "/com/canonical/landscape_settings/ConfigurationInterface"


class PermissionDeniedByPolicy(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.landscape_settings.PermissionDeniedByPolicy"
    

class ConfigurationMechanism(dbus.service.Object):

    def __init__(self, config, bus_name, conn=None):
        super(ConfigurationMechanism, self).__init__(
            conn, OBJECT_PATH, bus_name)
        self.dbus_info = None
        self.polkit = None
        self.config = config


    @dbus.service.method(INTERFACE_NAME,
                         in_signature="", out_signature="s",
                         sender_keyword="sender", connection_keyword="conn")
    def get_account_name(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, SERVICE_NAME):
            return "Foo"

    def _get_peer_pid(self, sender, conn):
        if self.dbus_info is None:
            self.dbus_info = dbus.Interface(conn.get_object('org.freedesktop.DBus',
                '/org/freedesktop/DBus/Bus', False), 'org.freedesktop.DBus')
        return self.dbus_info.GetConnectionUnixProcessID(sender)

    def _get_polkit(self):
        if self.polkit is None:
            self.polkit = dbus.Interface(dbus.SystemBus().get_object(
                'org.freedesktop.PolicyKit1',
                '/org/freedesktop/PolicyKit1/Authority', False),
                'org.freedesktop.PolicyKit1.Authority')
        else:
            return self.polkit

    def _is_local_call(self, sender, conn):
        """ 
        Check if this is a local call, implying it is within a secure context.
        """
        return sender is None and conn is None

    def _get_polkit_authorization(self, privilege):
        peer_pid = self._get_peer_pid(sender, conn)
        polkit = self._get_polkit()
        try:
            subject =  ('unix-process', 
                        {'pid': dbus.UInt32(pid, variant_level=1),
                         'start-time': dbus.UInt64(0, variant_level=1)})
            action_id = privilege
            details = {} 
            flags = dbus.UInt32(1)
            cancellation_id = ""
            return polkit.CheckAuthorization(
                subejct, 
                action_id, 
                details,
                flags, 
                cancellation_id, 
                timeout=600)
        except dbus.DBusException, e:
            if e._dbus_error_name == 'org.freedesktop.DBus.Error.ServiceUnknown':
                # This occurs on timeouts, so we retry
                polkit = None
                return self._get_polkit_authorization(privilege)
            else:
                raise
        
    def _is_allowed_by_policy(self, sender, conn, privilege):
        if self._is_local_call(sender, conn):
            return True
        (is_auth, _, details) = self._get_polkit_authorization(privilege)
        if not is_auth:
            raise PermissionDeniedByPolicy(privilege)
        


def listen():
    mainloop = gobject.MainLoop()
    print "Running example service."
    mainloop.run()


