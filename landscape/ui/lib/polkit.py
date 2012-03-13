import dbus
import dbus.service
import dbus.glib

from gi.repository import GObject


POLICY_NAME = "com.canonical.LandscapeClientSettings.configure"


class PolicyKitMechanism(dbus.service.Object):
    """
    L{PolicyKitMechanism} is a specialised L{dbus.service.Object} which
    provides PolicyKit authorization checks for a provided DBus bus name and
    object path.  Subclasses must therefore call l{__init__} here with their
    object path, bus name and an error class to be raised when permission
    escalation fails.

    @type object_path: string
    @param object_path: The object path to register the subclass with.
    @type bus_name: dbus.service.BusName
    @param bus_name: The L{BusName} to the register the subclass with.
    @type permission_error: dbus.DBusException
    @param permission_error: A L{dbus.DBusException} to be raised when
        PolicyKit authorisation fails for the client.
    """

    def __init__(self, object_path, bus_name, permission_error,
                 bypass=False, conn=None):
        super(PolicyKitMechanism, self).__init__(
            conn, object_path, bus_name)
        self.permission_error = permission_error
        self.dbus_info = None
        self.polkit = None
        self.bypass = bypass

    def _get_polkit_authorization(self, pid, privilege):
        """
        Check that the process with id L{pid} is allowed, by policy to utilise
        the L{privilege }.  If the class was initialised with L{bypass}=True
        then just say it was authorised without checking (useful for testing).
        """
        if self.bypass:
            return (True, None, "Bypass")
        polkit = dbus.Interface(dbus.SystemBus().get_object(
                'org.freedesktop.PolicyKit1',
                '/org/freedesktop/PolicyKit1/Authority', False),
                'org.freedesktop.PolicyKit1.Authority')
        subject = ('unix-process',
                   {'pid': dbus.UInt32(pid, variant_level=1),
                    'start-time': dbus.UInt64(0, variant_level=1)})
        action_id = privilege
        details = {"": ""}  # <- empty strings allow type inference
        flags = dbus.UInt32(1)
        cancellation_id = ""
        return polkit.CheckAuthorization(
            subject,
            action_id,
            details,
            flags,
            cancellation_id,
            timeout=15)

    def _get_peer_pid(self, sender, conn):
        """
        Get the process ID of the L{sender}.
        """
        if self.dbus_info is None:
            self.dbus_info = dbus.Interface(
                conn.get_object('org.freedesktop.DBus',
                '/org/freedesktop/DBus/Bus', False), 'org.freedesktop.DBus')
        return self.dbus_info.GetConnectionUnixProcessID(sender)

    def _is_local_call(self, sender, conn):
        """
        Check if this is a local call, implying it is within a secure context.
        """
        return (sender is None and conn is None)

    def _is_allowed_by_policy(self, sender, conn, privilege):
        """
        Check if we are already in a secure context, and if not check if the
        policy associated with L{privilege} both exists and allows the peer to
        utilise it.  As a side effect, if escalation of privileges is required
        then this will occur and a challenge will be generated if needs be.
        """
        if self._is_local_call(sender, conn):
            return True
        peer_pid = self._get_peer_pid(sender, conn)
        (is_auth, _, details) = self._get_polkit_authorization(peer_pid,
                                                               privilege)
        if not is_auth:
            raise self.permission_error(privilege)
        return True


def listen():
    """
    Invoke a L{gobject.MainLoop} to process incoming DBus events.
    """
    mainloop = GObject.MainLoop()
    mainloop.run()
