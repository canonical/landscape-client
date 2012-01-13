from landscape.tests.helpers import LandscapeTest, BrokerServiceHelper
from landscape.ui.model.registration import ObservableRegistration


class RegistrationTest(LandscapeTest):

    helpers = [BrokerServiceHelper]

    def setUp(self):
        super(RegistrationTest, self).setUp()

    def test_notify_observers(self):
        """
        Test that when an observer is registered it is called by
        L{notify_observers}.
        """
        observable = ObservableRegistration()
        notified = []
        notified_message = []
        notified_error = []

        def notify_me(message, error=False):
            notified.append(True)
            notified_message.append(message)
            notified_error.append(error)

        observable.register_notification_observer(notify_me)
        observable.notify_observers("Blimey", error=False)
        observable.notify_observers("Gor lummey!", error=True)
        self.assertEqual(notified, [True, True])
        self.assertEqual(notified_message, ["Blimey", "Gor lummey!"])
        self.assertTrue(notified_error, [False, True])

    def test_error_observers(self):
        """
        Test that when an error observer is registered it is called by
        L{error_observers}.
        """
        observable = ObservableRegistration()
        errored = []
        errored_error_list = []

        def error_me(error_list):
            errored.append(True)
            errored_error_list.append(error_list)

        observable.register_error_observer(error_me)
        observable.error_observers(["Ouch", "Dang"])
        self.assertTrue(errored, [True])
        self.assertEqual(errored_error_list, [["Ouch", "Dang"]])

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

        def failure(error=None):
            self.failed = True

        observable.register_fail_observer(failure)
        observable.fail()
        self.assertTrue(self.failed)
