from twisted.internet.defer import Deferred

from landscape.manager.manager import ManagerPluginRegistry
from landscape.manager.shutdownmanager import ShutdownManager
from landscape.tests.helpers import LandscapeIsolatedTest, RemoteBrokerHelper


class ShutdownManagerTest(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(ShutdownManagerTest, self).setUp()
        self.broker_service.message_store.set_accepted_types(["shutdown"])
        self.manager = ManagerPluginRegistry(
            self.broker_service.reactor, self.remote,
            self.broker_service.config, self.broker_service.bus)
        self.manager.add(ShutdownManager())

    def test_restart(self):
        """
        When a C{shutdown} message is received with a C{shutdown} directive set
        to C{False}, the C{shutdown} command should be called to restart the
        system 5 minutes from now.
        """
        run = self.mocker.replace("twisted.internet.utils.getProcessOutput")
        args = ["-r", "+5", "'Landscape is restarting down the system'"]
        getProcessOutput = self.expect(run("shutdown", args=args, path=None,
                                           errortoo=1))
        getProcessOutput.result(Deferred())
        self.mocker.replay()
        self.manager.dispatch_message({"type": "shutdown",
                                       "operation-id": 100,
                                       "reboot": True})

    def test_shutdown(self):
        """
        When a C{shutdown} message is received with a C{shutdown} directive set
        to C{True}, the C{shutdown} command should be called to shutdown the
        system 5 minutes from now.
        """
        run = self.mocker.replace("twisted.internet.utils.getProcessOutput")
        args = ["-h", "+5", "'Landscape is shutting down the system'"]
        getProcessOutput = self.expect(run("shutdown", args=args, path=None,
                                           errortoo=1))
        getProcessOutput.result(Deferred())
        self.mocker.replay()
        self.manager.dispatch_message({"type": "shutdown",
                                       "operation-id": 100,
                                       "reboot": False})
