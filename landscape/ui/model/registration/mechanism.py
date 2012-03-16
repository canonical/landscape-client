import subprocess
import sys
import os

import dbus
import dbus.service
import dbus.glib

from landscape.ui.lib.polkit import PolicyKitMechanism, POLICY_NAME


SERVICE_NAME = "com.canonical.LandscapeClientRegistration"
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
        try:
            message = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            self.register_notify(message)
            return True, message
        except subprocess.CalledProcessError, error:
            wait_phrase = "Please wait... "
            wait_phrase_index = error.output.find(wait_phrase)
            if wait_phrase_index > -1:
                message = error.output[wait_phrase_index + len(wait_phrase):]
            else:
                message = "Landscape configuration failed.\n%s" % error.output
            self.register_error(message)
            return False, message

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_notify(self, message):
        """
        L{register_notify} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_error(self, message):
        """
        L{register_error} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_succeed(self, message):
        """
        L{register_succeed} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='s')
    def register_fail(self, message):
        """
        L{register_fail} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

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
            succeed, message = self._do_registration(config_path)
            if succeed:
                message = "Registration message sent to Landscape server.\n"
                self.register_succeed(message)
                return (True, message)
            else:
                self.register_fail(message)
                return (False, message)

    def _do_disabling(self):
        cmd = ["landscape-config", "--disable"]
        try:
            subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            return True
        except subprocess.CalledProcessError:
            return False

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='')
    def disable_succeed(self):
        """
        L{disable_succeed} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

    @dbus.service.signal(dbus_interface=INTERFACE_NAME,
                         signature='')
    def disable_fail(self):
        """
        L{disable_fail} is a signal sent to subscribers.  It is not
        necessary for any actual work to occur in the method as it is called
        for the effect of invoking its decorator.
        """

    @dbus.service.method(INTERFACE_NAME,
                         in_signature="",
                         out_signature="b",
                         sender_keyword="sender",
                         connection_keyword="conn")
    def disable(self, sender=None, conn=None):
        if self._is_allowed_by_policy(sender, conn, POLICY_NAME):
            if self._do_disabling():
                self.disable_succeed()
                return True
            else:
                self.disable_fail()
                return False

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
