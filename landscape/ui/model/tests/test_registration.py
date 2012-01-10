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
        register_mock(ANY, ANY, ANY, success_handler_f=ANY)
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
        observable.register_notification_observer(notify_me)
        observable.notify_observers("Blimey", error=False)
        self.assertTrue(self.notified)
        self.assertEqual(self.notified_message, "Blimey")
        self.assertFalse(self.notified_error)
        observable.notify_observers("Gor lummey!", error=True)
        self.assertTrue(self.notified)
        self.assertEqual(self.notified_message, "Gor lummey!")
        self.assertTrue(self.notified_error)

    def test_error_observers(self):
        """
        Test that when an error observer is registered it is called by
        L{error_observers}.
        """
        observable = ObservableRegistration()
        self.errored = False
        self.errored_error_list = None
        def error_me(error_list):
            self.errored = True
            self.errored_error_list = error_list
        observable.register_error_observer(error_me)
        observable.error_observers(["Ouch", "Dang"])
        self.assertTrue(self.errored)
        self.assertEqual(self.errored_error_list, ["Ouch", "Dang"])

    def test_success_observers(self):
        """
        Test that when a success observer is registered it is called when
        L{succeed} is called on the model.
        """
        observable = ObservableRegistration()
        self.succeeded = False
        def success():
            self.succeeded = True
        observable.register_succeed_observer(success)
        observable.succeed()
        self.assertTrue(self.succeeded)


    def test_failure_observers(self):
        """
        Test that when a failure observer is registered it is called when
        L{fail} is called on the model.
        """
        observable = ObservableRegistration()
        self.failed = False
        def failure():
            self.failed = True
        observable.register_fail_observer(failure)
        observable.fail()
        self.assertTrue(self.failed)
