import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.registration.mechanism import (
    RegistrationMechanism, INTERFACE_NAME)
from landscape.ui.model.registration.proxy import RegistrationProxy



class RegistrationProxyTest(LandscapeTest):

    def setUp(self):
        super(RegistrationProxyTest, self).setUp()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)

        def _do_registration(this, config_path):
                return 0

        RegistrationMechanism._do_registration = _do_registration
        self.mechanism = RegistrationMechanism(bus_name)

        def setup_interface(this, bus):
            """
            This just allows us to test without actually relying on dbus.
            """
            this._interface = self.mechanism

        RegistrationProxy._setup_interface = setup_interface
        self.proxy = RegistrationProxy()

    def tearDown(self):
        self.mechanism.remove_from_connection()
        super(RegistrationProxyTest, self).tearDown()

    def test_register(self):
        self.assertEquals(self.proxy.register("foo"), (True, "Connected\n"))

    def test_poll(self):
        self.mechanism.error_list.append("Broke it")
        self.mechanism.message_list.append("Fixed it")
        self.assertEqual(self.proxy.poll(), {"error": ["", "Broke it"],
                                             "message": ["", "Fixed it"]})
        self.assertEqual(self.proxy.poll(), {"error": [""],
                                             "message": [""]})

    
