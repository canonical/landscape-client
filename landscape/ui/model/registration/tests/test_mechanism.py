import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.registration.mechanism import (
    RegistrationMechanism, INTERFACE_NAME)


class MechanismTest(LandscapeTest):

    def setUp(self):
        super(MechanismTest, self).setUp()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus(private=True)
        self.bus_name = dbus.service.BusName(INTERFACE_NAME, bus)

    def make_registration(self, succeed):
        def _do_registration(this, config_path):
            if succeed:
                return 0
            else:
                return 1
        return _do_registration

    def test_registration_succeed(self):
        RegistrationMechanism._do_registration = self.make_registration(True)
        mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual(mechanism.register("foo"), (True, "Connected\n"))

    def test_registration_fail(self):
        RegistrationMechanism._do_registration = self.make_registration(False)
        mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual(mechanism.register("foo"),
                         (False, "Failed to connect [code 1]\n"))
