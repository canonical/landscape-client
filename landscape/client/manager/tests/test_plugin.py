from twisted.internet.defer import Deferred

from landscape.client.manager.plugin import FAILED
from landscape.client.manager.plugin import ManagerPlugin, DataWatcherManager
from landscape.client.manager.plugin import SUCCEEDED
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class BrokerPluginTest(LandscapeTest):

    helpers = [ManagerHelper]

    def test_call_with_operation_result_success(self):
        """
        A helper method exists which calls a function and sends an
        operation-result message based on the success of that method.
        """
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        broker_service = self.broker_service
        broker_service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 12312}

        def operation():
            return None

        def assert_messages(ignored):
            messages = broker_service.message_store.get_pending_messages()
            self.assertMessages(
                messages,
                [
                    {
                        "type": "operation-result",
                        "status": SUCCEEDED,
                        "operation-id": 12312,
                    },
                ],
            )

        result = plugin.call_with_operation_result(message, operation)
        return result.addCallback(assert_messages)

    def test_call_with_operation_result_error(self):
        """
        The helper for operation-results sends an appropriate message when an
        exception is raised from the given method.
        """
        self.log_helper.ignore_errors(RuntimeError)
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        broker_service = self.broker_service
        broker_service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 12312}

        def operation():
            raise RuntimeError("What the crap!")

        def assert_messages(ignored):
            messages = broker_service.message_store.get_pending_messages()
            self.assertMessages(
                messages,
                [
                    {
                        "type": "operation-result",
                        "status": FAILED,
                        "result-text": "RuntimeError: What the crap!",
                        "operation-id": 12312,
                    },
                ],
            )
            logdata = self.logfile.getvalue()
            self.assertTrue("RuntimeError: What the crap!" in logdata, logdata)

        result = plugin.call_with_operation_result(message, operation)
        return result.addCallback(assert_messages)

    def test_call_with_operation_result_exchanges_urgently(self):
        """
        Operation results are reported to the server as quickly as possible.
        """
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        broker_service = self.broker_service
        broker_service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 123}

        def operation():
            return None

        def assert_urgency(ignored):
            self.assertTrue(broker_service.exchanger.is_urgent())

        result = plugin.call_with_operation_result(message, operation)
        return result.addCallback(assert_urgency)

    def test_callable_returning_a_deferred(self):
        """
        The callable parameter can return a C{Deferred}.
        """
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        broker_service = self.broker_service
        broker_service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 12312}
        deferred = Deferred()

        def operation():
            return deferred

        def assert_messages(ignored):
            messages = broker_service.message_store.get_pending_messages()
            self.assertMessages(
                messages,
                [
                    {
                        "type": "operation-result",
                        "result-text": "blah",
                        "status": SUCCEEDED,
                        "operation-id": 12312,
                    },
                ],
            )

        result = plugin.call_with_operation_result(message, operation)
        result.addCallback(assert_messages)
        deferred.callback("blah")
        return result


class StubDataWatchingPlugin(DataWatcherManager):

    message_type = "wubble"

    def __init__(self, data=None):
        self.data = data

    def get_data(self):
        return self.data


class DataWatcherManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.plugin = StubDataWatchingPlugin("hello world")
        self.plugin.register(self.manager)

    def test_get_message(self):
        self.assertEqual(
            self.plugin.get_new_data(),
            "hello world",
        )

    def test_get_message_unchanging(self):
        self.assertEqual(
            self.plugin.get_new_data(),
            "hello world",
        )
        self.assertEqual(self.plugin.get_new_data(), None)
