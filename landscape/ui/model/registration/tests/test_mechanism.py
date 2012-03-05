import dbus

from landscape.ui.model.registration.mechanism import (
    RegistrationMechanism, INTERFACE_NAME)
from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import (
    got_gobject_introspection, gobject_skip_message)


class MechanismTest(LandscapeTest):
    """
    L{MechanismTest} mocks out the actual registration process and allows us to
    simply and quickly check the outputs of registration that are relied on
    elsewhere.
    """

    def setUp(self):
        super(MechanismTest, self).setUp()
        self.bus_name = dbus.service.BusName(INTERFACE_NAME, MechanismTest.bus)
        self.mechanism = None

    def tearDown(self):
        if not self.mechanism is None:
            self.mechanism.remove_from_connection()
        super(MechanismTest, self).tearDown()

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
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual((True, "Connected\n"), self.mechanism.register("foo"))

    def test_registration_fail(self):
        """
        Test we get appropriate feedback from a failed connection when we
        call L{register} synchronously.
        """
        RegistrationMechanism._do_registration = self.make_registration(False)
        self.mechanism = RegistrationMechanism(self.bus_name)
        self.assertEqual((False, "Failed to connect\n"),
                         self.mechanism.register("foo"))

    if not got_gobject_introspection:
        skip = gobject_skip_message
    else:
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        try:
            bus = dbus.SessionBus(private=True)
        except dbus.exceptions.DBusException:
            skip_string = "Cannot launch private DBus session without X11"
            test_registration_succeed.skip = skip_string
            test_registration_fail.skip = skip_string
