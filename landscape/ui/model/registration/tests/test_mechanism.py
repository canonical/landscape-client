import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.registration.mechanism import (
    RegistrationMechanism, INTERFACE_NAME)


class MechanismTest(LandscapeTest):
    """
    L{MechanismTest} mocks out the actual registration process and allows us to
    simply and quickly check the outputs of registration that are relied on
    elsewhere.
    """

    def setUp(self):
        super(MechanismTest, self).setUp()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus(private=True)
        self.bus_name = dbus.service.BusName(INTERFACE_NAME, bus)

    def make_registration(self, succeed):

        def _do_registration(this, config_path):
            return succeed

        return _do_registration

    def test_registration_succeed(self):
        """
        Test we get appropriate feedback from a successful connection when we
        call L{register} synchronously.
        """
        RegistrationMechanism._do_registration = self.make_registration(True)
        mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual(mechanism.register("foo"), (True, "Connected\n"))

    def test_registration_fail(self):
        """
        Test we get appropriate feedback from a failed connection when we
        call L{register} synchronously.
        """
        RegistrationMechanism._do_registration = self.make_registration(False)
        mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual(mechanism.register("foo"),
                         (False, "Failed to connect\n"))
