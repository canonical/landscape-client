from landscape.manager.manager import ManagerPluginRegistry
from landscape.manager.rebootmanager import RebootManager, RebootError
from landscape.tests.helpers import LandscapeIsolatedTest, RemoteBrokerHelper


class RebootManagerTest(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(RebootManagerTest, self).setUp()
        self.broker_service.message_store.set_accepted_types(["reboot"])
        self.manager = ManagerPluginRegistry(
            self.broker_service.reactor, self.remote,
            self.broker_service.config, self.broker_service.bus)
        self.manager.add(RebootManager())

    def test_restart(self):
        """
        When a C{reboot} message is received with a C{restart} directive, the
        C{shutdown} command should be called.
        """
        system = self.mocker.replace("os.system")
        command = "shutdown -r +5 'Landscape is restarting the system'"
        self.expect(system(command)).result(0)
        self.mocker.replay()
        self.manager.dispatch_message({"type": "reboot", "shutdown": False})

    def test_shutdown(self):
        """
        When a C{reboot} message is received with a C{shutdown} directive, the
        C{shutdown} command should be called.
        """
        system = self.mocker.replace("os.system")
        command = "shutdown -h +5 'Landscape is shutting down the system'"
        self.expect(system(command)).result(0)
        self.mocker.replay()
        self.manager.dispatch_message({"type": "reboot", "shutdown": True})

    def test_raise_reboot_error_on_non_zero_result(self):
        """
        If the call to shutdown returns a non-zero exit value a L{RebootError}
        is raised.
        """
        self.log_helper.ignore_errors(RebootError)
        system = self.mocker.replace("os.system")
        command = "shutdown -h +5 'Landscape is shutting down the system'"
        self.expect(system(command)).result(1)
        self.mocker.replay()
        self.manager.dispatch_message({"type": "reboot", "shutdown": True})
        self.assertIn(
            "RebootError: 'shutdown' returned a non-zero exit value.",
            self.logfile.getvalue())
