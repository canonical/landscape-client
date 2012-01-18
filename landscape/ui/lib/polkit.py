import dbus
import dbus.service
import dbus.glib
import gobject


class PolicyKitMechanism(dbus.service.Object):

    def __init__(self, object_path, bus_name, permission_error, 
                 bypass=False, conn=None):
        super(PolicyKitMechanism, self).__init__(
            conn, object_path, bus_name)
        self.permission_error = permission_error
        self.dbus_info = None
        self.polkit = None
        self.bypass = bypass

    def _get_polkit_authorization(self, pid, privilege):
        if self.bypass:
            return (True, None, "Bypass")
        polkit = self._get_polkit()
        try:
            subject = ('unix-process',
                       {'pid': dbus.UInt32(pid, variant_level=1),
                        'start-time': dbus.UInt64(0, variant_level=1)})
            action_id = privilege
            details = {"": ""}
            flags = dbus.UInt32(1)
            cancellation_id = ""
            return polkit.CheckAuthorization(
                subject,
                action_id,
                details,
                flags,
                cancellation_id,
                timeout=600)
        except dbus.DBusException, err:
            # raise
            if (err._dbus_error_name ==
                'org.freedesktop.DBus.Error.ServiceUnknown'):
                # This occurs on timeouts, so we retry
                polkit = None
                return self._get_polkit_authorization(pid, privilege)
            else:
                raise

    def _get_peer_pid(self, sender, conn):
        if self.dbus_info is None:
            self.dbus_info = dbus.Interface(
                conn.get_object('org.freedesktop.DBus',
                '/org/freedesktop/DBus/Bus', False), 'org.freedesktop.DBus')
        return self.dbus_info.GetConnectionUnixProcessID(sender)

    def _get_polkit(self):
        if self.polkit is None:
            self.polkit = dbus.Interface(dbus.SystemBus().get_object(
                'org.freedesktop.PolicyKit1',
                '/org/freedesktop/PolicyKit1/Authority', False),
                'org.freedesktop.PolicyKit1.Authority')
        return self.polkit

    def _is_local_call(self, sender, conn):
        """
        Check if this is a local call, implying it is within a secure context.
        """
        return (sender is None and conn is None)

    def _is_allowed_by_policy(self, sender, conn, privilege):
        if self._is_local_call(sender, conn):
            return True
        peer_pid = self._get_peer_pid(sender, conn)
        (is_auth, _, details) = self._get_polkit_authorization(peer_pid,
                                                               privilege)
        if not is_auth:
            raise self.permission_error(privilege)
        return True


def listen():
    mainloop = gobject.MainLoop()
    mainloop.run()
