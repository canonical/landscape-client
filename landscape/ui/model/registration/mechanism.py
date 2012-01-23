import select
import subprocess
import os

import dbus
import dbus.service
import dbus.glib
from landscape.ui.lib.polkit import PolicyKitMechanism


SERVICE_NAME = "com.canonical.LandscapeClientRegistration"
POLICY_NAME = SERVICE_NAME + ".register"
INTERFACE_NAME = \
    "com.canonical.LandscapeClientRegistration.RegistrationInterface"
OBJECT_PATH = \
    "/com/canonical/LandscapeClientRegistration/RegistrationInterface"


class PermissionDeniedByPolicy(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.LandscapeClientRegistration.PermissionDeniedByPolicy"


class RegistrationError(dbus.DBusException):
    _dbus_error_name = \
        "com.canonical.LandscapeClientRegistration.RegistrationError"


class RegistrationMechanism(PolicyKitMechanism):
    """
    L{RegistrationMechanism} is a mechanism for invoking and observing client
    registration over DBus.  It utilises PolicyKit to ensure that only
    administrative users may use it.
    """

    def __init__(self, bus_name, bypass=False, conn=None):
        super(RegistrationMechanism, self).__init__(
            OBJECT_PATH, bus_name, PermissionDeniedByPolicy,
            bypass=bypass, conn=conn)
        self.process = None
        self.message_queue = []
        self.error_queue = []

    def _do_registration(self, config_path):
        self.register_notify("Trying to register ...\n")
        cmd = ["landscape-config", "--silent", "-c",
               os.path.abspath(config_path)]
        self.process = subprocess.Popen(cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE)
        return_code = None
        while return_code is None:
            readables, w, x = select.select(
                [self.process.stdout, self.process.stderr], [], [], 0)
            for readable in readables:
                message = readable.readline()
                if readable is self.process.stdout:
                    self.register_notify(message)
                else:
                    self.register_error(message)
            return_code = self.process.poll()
        return return_code

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_notify(self, message):
        """
        L{register_notify} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """
        pass

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_error(self, message):
        """
        L{register_error} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """
        pass

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_succeed(self, message):
        """
        L{register_succeed} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """
        pass

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_fail(self, message):
        """
        L{register_fail} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """
        pass

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="",
                         out_signature="b",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def challenge(self, sender=None, conn=None):
        """
        Safely check if we can escalate permissions.
        """
        try:
            return self._is_allowed_by_policy(sender, conn, POLICY_NAME)
        except PermissionDeniedByPolicy:
            return False

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="s",
                         out_signature="(bs)",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def register(self, config_path, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            return_code = self._do_registration(config_path)
            if return_code == 0:
                message = "Connected\n"
                self.register_succeed(message)
                return (True, message)
            else:
                message = "Failed to connect [code %s]\n" % str(return_code)
                self.register_fail(message)
                return (False, message)
