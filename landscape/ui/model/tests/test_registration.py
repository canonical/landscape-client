from landscape.configuration import register
from landscape.reactor import TwistedReactor
from landscape.sysvconfig import SysVConfig
from landscape.tests.helpers import LandscapeTest, BrokerServiceHelper
from landscape.tests.mocker import ANY
from landscape.ui.model.registration import ObservableRegistration
from landscape.ui.model.configuration import LandscapeSettingsConfiguration


class RegistrationTest(LandscapeTest):

    helpers = [BrokerServiceHelper]

    def setUp(self):
        super(RegistrationTest, self).setUp()

    def test_register(self):
        """
        Test that a valid config will result in register calling though to the
        underlying registration in L{landscape.configuration.register}.
        """
        observable_registration = ObservableRegistration()
        service = self.broker_service
        sysvconfig_mock = self.mocker.patch(SysVConfig)
        register_mock = self.mocker.replace(register, passthrough=False)
        self.mocker.order()
        sysvconfig_mock.set_start_on_boot(True)
        sysvconfig_mock.restart_landscape()
        register_mock(ANY, ANY, ANY)
        self.mocker.replay()
        observable_registration.register(service.config)

    def test_notify_observers(self):
        """
        Test that when an observer is registered it is called by
        L{notify_observers}.
        """
        observable = ObservableRegistration()
        self.notified = False
        self.notified_message = None
        self.notified_error = False
        def notify_me(message, error=False):
            self.notified = True
            self.notified_message = message
            self.notified_error = error
        observable.register_notifiable(notify_me)
        observable.notify_observers("Blimey", error=False)
        self.assertTrue(self.notified)
        self.assertEqual(self.notified_message, "Blimey")
        self.assertFalse(self.notified_error)
        observable.notify_observers("Gor lummey!", error=True)
        self.assertTrue(self.notified)
        self.assertEqual(self.notified_message, "Gor lummey!")
        self.assertTrue(self.notified_error)

    def test_fail_observers(self):
        """
        Test that when an failure observer is registered it is called by
        L{fail_observers}.
        """
        observable = ObservableRegistration()
        self.failed = False
        self.failed_error_list = None
        def fail_me(error_list):
            self.failed = True
            self.failed_error_list = error_list
        observable.register_failable(fail_me)
        observable.fail_observers(["Ouch", "Dang"])
        self.assertTrue(self.failed)
        self.assertEqual(self.failed_error_list, ["Ouch", "Dang"])

        
