from unittest.mock import patch
from twisted.internet import task

from landscape.client.manager.shutdownmanager import ShutdownManager
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import ManagerHelper


class ShutdownManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super().setUp()

        self.broker_service.message_store.set_accepted_types(
            ["shutdown", "operation-result"],
        )
        self.broker_service.pinger.start()

        self.clock = task.Clock()
        self.plugin = ShutdownManager()
        self.plugin.reactor = self.clock

        self.manager.add(self.plugin)

    def tearDown(self):
        return super().tearDown()

    @patch('landscape.client.manager.shutdownmanager.ShutdownManager._Reboot')
    def test_reboot(self, mock_reboot):
        message = {"type": "shutdown", "reboot": True, "operation-id": 100}
        deferred = self.plugin._handle_shutdown(message)

        mock_reboot.assert_called_once()
        return deferred

    @patch('landscape.client.manager.shutdownmanager.reactor')
    def test_shutdown(self, mock_reactor):

        message = {"type": "shutdown", "reboot": False, "operation-id": 101}
        self.plugin._handle_shutdown(message)

        mock_reactor.callLater.assert_called_once()

        # check it was the shutdown method requested
        arg = mock_reactor.callLater.call_args.args[1]
        name = getattr(arg, "__name__", str(arg))
        self.assertEqual(name, "_Shutdown")
