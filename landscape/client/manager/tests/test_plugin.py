from twisted.internet.defer import Deferred

from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper
from landscape.client.manager.plugin import ManagerPlugin, SUCCEEDED, FAILED


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
        operation = (lambda: None)

        def assert_messages(ignored):
            messages = broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "status": SUCCEEDED,
                                  "operation-id": 12312}])

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
            self.assertMessages(messages,
                                [{"type": "operation-result", "status": FAILED,
                                  "result-text": "RuntimeError: What the "
                                  "crap!", "operation-id": 12312}])
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
        operation = (lambda: None)

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
        operation = (lambda: deferred)

        def assert_messages(ignored):
            messages = broker_service.message_store.get_pending_messages()
            self.assertMessages(messages,
                                [{"type": "operation-result",
                                  "result-text": "blah",
                                  "status": SUCCEEDED,
                                  "operation-id": 12312}])

        result = plugin.call_with_operation_result(message, operation)
        result.addCallback(assert_messages)
        deferred.callback("blah")
        return result
