import dbus

import landscape.ui.model.registration.mechanism as mechanism


class RegistrationProxy(object):
    """
    L{RegistrationProxy} allows the use of the L{RegistrationMechanism} via
    DBus without having to know about DBus.  This in turn allows controller
    code to remain agnostic to the implementation of registration.
    """

    def __init__(self, on_register_notify=None, on_register_error=None,
                 on_register_succeed=None, on_register_fail=None,
                 on_disable_succeed=None, on_disable_fail=None, bus=None):
        self._bus = None
        self._interface = None
        self._on_register_notify = on_register_notify
        self._on_register_error = on_register_error
        self._on_register_succeed = on_register_succeed
        self._on_register_fail = on_register_fail
        self._on_disable_succeed = on_disable_succeed
        self._on_disable_fail = on_disable_fail
        self._setup_interface(bus)

    def _setup_interface(self, bus):
        """
        Redefining L{_setup_interface} allows us to bypass DBus for more
        convenient testing in some instances.
        """
        if bus is None:
            self._bus = dbus.SystemBus()
        else:
            self._bus = bus
        self._remote_object = self._bus.get_object(mechanism.SERVICE_NAME,
                                                   mechanism.OBJECT_PATH)
        self._interface = dbus.Interface(self._remote_object,
                                         mechanism.INTERFACE_NAME)

    def _exit_handler_wrapper(self, exit_handler):

        def wrapped_exit_handler(message):
            self._remove_handlers()
            exit_handler(message)

        return wrapped_exit_handler

    def _register_handlers(self):
        self._handlers = []
        if self._on_register_notify:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._on_register_notify,
                    signal_name="register_notify",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))
        if self._on_register_error:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._on_register_error,
                    signal_name="register_error",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))
        if self._on_register_succeed:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._exit_handler_wrapper(self._on_register_succeed),
                    signal_name="register_succeed",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))
        if self._on_register_fail:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._exit_handler_wrapper(self._on_register_fail),
                    signal_name="register_fail",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))
        if self._on_disable_succeed:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._exit_handler_wrapper(self._on_disable_succeed),
                    signal_name="disable_succeed",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))
        if self._on_disable_fail:
            self._handlers.append(
                self._bus.add_signal_receiver(
                    self._exit_handler_wrapper(self._on_disable_fail),
                    signal_name="disable_fail",
                    dbus_interface=mechanism.INTERFACE_NAME,
                    bus_name=None,
                    path=mechanism.OBJECT_PATH))

    def _remove_handlers(self):
        for handler in self._handlers:
            self._bus.remove_signal_receiver(handler)

    def challenge(self):
        return self._interface.challenge()

    def register(self, config_path):
        self._register_handlers()
        try:
            result, message = self._interface.register(config_path)
        except dbus.DBusException, e:
            if e.get_dbus_name() != "org.freedesktop.DBus.Error.NoReply":
                raise
            else:
                result = False
                message = "Registration timed out."
        if result:
            self._on_register_succeed()
        else:
            self._on_register_error(message)
        return result

    def disable(self):
        self._register_handlers()
        result = self._interface.disable()
        if result:
            self._on_disable_succeed()
        else:
            self._on_disable_fail()
        return result

    def exit(self):
        """
        Cause the mechanism to exit.
        """
        try:
            self._interface.exit()
        except dbus.DBusException, e:
            if e.get_dbus_name() != "org.freedesktop.DBus.Error.NoReply":
                raise
