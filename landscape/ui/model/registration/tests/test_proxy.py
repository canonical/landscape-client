import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.registration.mechanism import (
    RegistrationMechanism, INTERFACE_NAME)
from landscape.ui.model.registration.proxy import RegistrationProxy


class RegistrationProxyTest(LandscapeTest):
    """
    L{RegistrationProxyTest} bypasses DBus to simply check the interface
    between the proxy and the mechanism it would usually contact via DBus.
    """

    def setUp(self):
        super(RegistrationProxyTest, self).setUp()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus(True)
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)

        def _do_registration(this, config_path):
            return True

        RegistrationMechanism._do_registration = _do_registration
        self.mechanism = RegistrationMechanism(bus_name)

        def setup_interface(this, bus):
            """
            This just allows us to test without actually relying on dbus.
            """
            this._interface = self.mechanism

        def register_handlers(this):
            pass

        def remove_handlers(this):
            pass

        def callback(message):
            pass

        RegistrationProxy._setup_interface = setup_interface
        RegistrationProxy._register_handlers = register_handlers
        RegistrationProxy._remove_handlers = remove_handlers
        self.proxy = RegistrationProxy(callback, callback, callback, callback)

    def tearDown(self):
        self.mechanism.remove_from_connection()
        super(RegistrationProxyTest, self).tearDown()

    def test_register(self):
        """
        Test that the proxy calls through to the underlying interface and
        correctly performs registration.
        """
        return self.assertEquals(self.proxy.register("foo"),
                                 (True, "Connected\n"))
