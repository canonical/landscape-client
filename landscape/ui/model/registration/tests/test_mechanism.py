import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import dbus_test_should_skip, dbus_skip_message
if not dbus_test_should_skip:
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
        self.mechanism = None

    def tearDown(self):
        if not self.mechanism is None:
            self.mechanism.remove_from_connection()
        super(MechanismTest, self).tearDown()

    def make_fake_registration(self, succeed, message=""):
        """
        Return a fake registration method that will fail or succeed by
        returning L{succeed} (a boolean).
        """

        def _do_registration(this, config_path):
            return succeed, message

        return _do_registration

    def make_fake_disabling(self, succeed):
        """
        Return a fake disabling method that will fail or succeed by
        returning L{succeed} (a boolean).
        """

        def _do_disabling(this):
            return succeed

        return _do_disabling

    def test_registration_succeed(self):
        """
        Test we get appropriate feedback from a successful connection when we
        call L{register} synchronously.
        """
        RegistrationMechanism._do_registration = self.make_fake_registration(
            True)
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual(
            (True, "Registration message sent to Landscape server.\n"),
            self.mechanism.register("foo"))

    def test_registration_fail(self):
        """
        Test we get appropriate feedback from a failed connection when we
        call L{register} synchronously.
        """
        RegistrationMechanism._do_registration = self.make_fake_registration(
            False, "boom")
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual((False, "boom"),
                         self.mechanism.register("foo"))

    def test_disabling_succeed(self):
        """
        Test we get True from a failed disabling when we call L{disable}
        synchronously.
        """
        RegistrationMechanism._do_disabling = self.make_fake_disabling(True)
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertTrue(self.mechanism.disable())

    def test_disabling_fail(self):
        """
        Test we get False from a failed disabling when we call L{disable}
        synchronously.
        """
        RegistrationMechanism._do_disabling = self.make_fake_disabling(False)
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertFalse(self.mechanism.disable())

    def test_exit(self):
        """
        Test that we cause the mechanism to exit.
        """
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertRaises(SystemExit, self.mechanism.exit)

    if dbus_test_should_skip:
        skip = dbus_skip_message
