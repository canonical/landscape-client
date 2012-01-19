import dbus

import landscape.ui.model.registration.mechanism as mechanism


class RegistrationProxy(object):

    def __init__(self, on_notify, on_error,
                 on_succeed, on_fail, bus=None):
        self._bus = None
        self._interface = None
        self._on_notify = on_notify
        self._on_error = on_error
        self._on_succeed = on_succeed
        self._on_fail = on_fail
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
        self._handlers = [
            self._bus.add_signal_receiver(
                self._on_notify,
                signal_name="register_notify",
                dbus_interface=mechanism.INTERFACE_NAME,
                bus_name=None,
                path=mechanism.OBJECT_PATH),
            self._bus.add_signal_receiver(
                self._on_error,
                signal_name="register_error",
                dbus_interface=mechanism.INTERFACE_NAME,
                bus_name=None,
                path=mechanism.OBJECT_PATH),
            self._bus.add_signal_receiver(
                self._exit_handler_wrapper(self._on_succeed),
                signal_name="register_succeed",
                dbus_interface=mechanism.INTERFACE_NAME,
                bus_name=None,
                path=mechanism.OBJECT_PATH),
            self._bus.add_signal_receiver(
                self._exit_handler_wrapper(self._on_fail),
                signal_name="register_fail",
                dbus_interface=mechanism.INTERFACE_NAME,
                bus_name=None,
                path=mechanism.OBJECT_PATH)
            ]

    def _remove_handlers(self):
        for handler in self._handlers:
            self._bus.remove_signal_receiver(handler)

    def challenge(self):
        return self._interface.challenge()

    def register(self, config_path, reply_handler=None, error_handler=None):
        self._register_handlers()
        if self._bus:
            return self._interface.register(config_path,
                                            reply_handler=reply_handler,
                                            error_handler=error_handler)
        else:
            return self._interface.register(config_path)
