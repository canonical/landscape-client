from twisted.internet.defer import Deferred

from landscape.manager.deployment import ManagerService, ManagerConfiguration
from landscape.manager.manager import (
    ManagerPlugin, ManagerDBusObject, SUCCEEDED, FAILED)

from landscape.lib.dbus_util import get_object

from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, ManagerHelper)


class PluginOperationResultTest(LandscapeTest):

    helpers = [ManagerHelper]

    def test_call_with_operation_result_success(self):
        """
        A helper method exists which calls a function and sends an
        operation-result message based on the success of that method.
        """
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 12312}
        def operation():
            pass
        plugin.call_with_operation_result(message, operation)
        messages = self.broker_service.message_store.get_pending_messages()
        self.assertMessages(messages,
                            [{"type": "operation-result", "status": SUCCEEDED,
                              "operation-id": 12312}])

    def test_call_with_operation_result_error(self):
        """
        The helper for operation-results sends an appropriate message when an
        exception is raised from the given method.
        """
        self.log_helper.ignore_errors(RuntimeError)
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 12312}
        def operation():
            raise RuntimeError("What the crap!")
        plugin.call_with_operation_result(message, operation)
        messages = self.broker_service.message_store.get_pending_messages()
        self.assertMessages(messages,
                            [{"type": "operation-result", "status": FAILED,
                              "result-text": "RuntimeError: What the crap!",
                              "operation-id": 12312}])

        logdata = self.logfile.getvalue()
        self.assertTrue("RuntimeError: What the crap!" in logdata, logdata)

    def test_call_with_operation_result_exchanges_urgently(self):
        """
        Operation results are reported to the server as quickly as possible.
        """
        plugin = ManagerPlugin()
        plugin.register(self.manager)
        service = self.broker_service
        service.message_store.set_accepted_types(["operation-result"])
        message = {"operation-id": 123}
        def operation():
            pass
        plugin.call_with_operation_result(message, operation)
        self.assertTrue(service.exchanger.is_urgent())


class ManagerDBusObjectTest(LandscapeIsolatedTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(ManagerDBusObjectTest, self).setUp()
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.makeFile(), "--bus", "session",
                            "--manager-plugins", "ProcessKiller"])
        self.manager_service = ManagerService(configuration)
        self.broker_service.startService()
        self.manager_service.startService()
        self.dbus_object = get_object(self.broker_service.bus,
                                      ManagerDBusObject.bus_name,
                                      ManagerDBusObject.object_path)

    def tearDown(self):
        super(ManagerDBusObjectTest, self).tearDown()
        self.broker_service.stopService()

    def test_ping(self):
        result = self.dbus_object.ping()
        def got_result(result):
            self.assertEquals(result, True)
        return result.addCallback(got_result)

    def test_exit(self):
        result = Deferred()
        reactor = self.mocker.replace("twisted.internet.reactor")
        self.expect(reactor.stop()).call(lambda: result.callback(None))
        self.mocker.replay()
        self.dbus_object.exit()
        return result
