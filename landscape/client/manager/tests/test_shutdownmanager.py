from twisted.python.failure import Failure
from twisted.internet.error import ProcessTerminated, ProcessDone
from twisted.internet.protocol import ProcessProtocol

from landscape.lib.testing import StubProcessFactory
from landscape.client.manager.plugin import SUCCEEDED, FAILED
from landscape.client.manager.shutdownmanager import (
    ShutdownManager, ShutdownProcessProtocol)
from landscape.client.tests.helpers import LandscapeTest, ManagerHelper


class ShutdownManagerTest(LandscapeTest):

    helpers = [ManagerHelper]

    def setUp(self):
        super(ShutdownManagerTest, self).setUp()
        self.broker_service.message_store.set_accepted_types(
            ["shutdown", "operation-result"])
        self.broker_service.pinger.start()
        self.process_factory = StubProcessFactory()
        self.plugin = ShutdownManager(process_factory=self.process_factory)
        self.manager.add(self.plugin)

    def test_restart(self):
        """
        C{shutdown} processes run until the shutdown is to be performed.  The
        L{ShutdownProcessProtocol} watches a process for errors, for 10
        seconds by default, and if none occur the activity is marked as
        L{SUCCEEDED}.  Data printed by the process is included in the
        activity's result text.
        """
        message = {"type": "shutdown", "reboot": True, "operation-id": 100}
        self.plugin.perform_shutdown(message)
        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        self.assertTrue(isinstance(protocol, ShutdownProcessProtocol))
        self.assertEqual(
            arguments[1:3],
            ("/sbin/shutdown", ["/sbin/shutdown", "-r", "+4",
                                "Landscape is rebooting the system"]))

        def restart_performed(ignore):
            self.assertTrue(self.broker_service.exchanger.is_urgent())
            self.assertEqual(
                self.broker_service.message_store.get_pending_messages(),
                [{"type": "operation-result", "api": b"3.2",
                  "operation-id": 100, "timestamp": 10, "status": SUCCEEDED,
                  "result-text": u"Data may arrive in batches."}])

        protocol.result.addCallback(restart_performed)
        protocol.childDataReceived(0, b"Data may arrive ")
        protocol.childDataReceived(0, b"in batches.")
        # We need to advance both reactors to simulate that fact they
        # are loosely in sync with each other
        self.broker_service.reactor.advance(10)
        self.manager.reactor.advance(10)
        return protocol.result

    def test_shutdown(self):
        """
        C{shutdown} messages have a flag that indicates whether a reboot or
        shutdown has been requested.  The C{shutdown} command is called
        appropriately.
        """
        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        self.plugin.perform_shutdown(message)
        [arguments] = self.process_factory.spawns
        self.assertEqual(
            arguments[1:3],
            ("/sbin/shutdown", ["/sbin/shutdown", "-h", "+4",
                                "Landscape is shutting down the system"]))

    def test_restart_fails(self):
        """
        If an error occurs before the error checking timeout the activity will
        be failed.  Data printed by the process prior to the failure is
        included in the activity's result text.
        """
        message = {"type": "shutdown", "reboot": True, "operation-id": 100}
        self.plugin.perform_shutdown(message)

        def restart_failed(message_id):
            self.assertTrue(self.broker_service.exchanger.is_urgent())
            messages = self.broker_service.message_store.get_pending_messages()
            self.assertEqual(len(messages), 1)
            message = messages[0]
            self.assertEqual(message["type"], "operation-result")
            self.assertEqual(message["api"], b"3.2")
            self.assertEqual(message["operation-id"], 100)
            self.assertEqual(message["timestamp"], 0)
            self.assertEqual(message["status"], FAILED)
            self.assertIn(u"Failure text is reported.", message["result-text"])

            # Check that after failing, we attempt to force the shutdown by
            # switching the binary called
            [spawn1_args, spawn2_args] = self.process_factory.spawns
            protocol = spawn2_args[0]
            self.assertIsInstance(protocol, ProcessProtocol)
            self.assertEqual(spawn2_args[1:3],
                             ("/sbin/reboot", ["/sbin/reboot"]))

        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.result.addCallback(restart_failed)
        protocol.childDataReceived(0, b"Failure text is reported.")
        protocol.processEnded(Failure(ProcessTerminated(exitCode=1)))
        return protocol.result

    def test_process_ends_after_timeout(self):
        """
        If the process ends after the error checking timeout has passed
        C{result} will not be re-fired.
        """
        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        self.plugin.perform_shutdown(message)

        stash = []

        def restart_performed(ignore):
            self.assertEqual(stash, [])
            stash.append(True)

        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.result.addCallback(restart_performed)
        self.manager.reactor.advance(10)
        protocol.processEnded(Failure(ProcessTerminated(exitCode=1)))
        return protocol.result

    def test_process_data_is_not_collected_after_firing_result(self):
        """
        Data printed in the sub-process is not collected after C{result} has
        been fired.
        """
        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        self.plugin.perform_shutdown(message)

        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.childDataReceived(0, b"Data may arrive ")
        protocol.childDataReceived(0, b"in batches.")
        self.manager.reactor.advance(10)
        self.assertEqual(protocol.get_data(), "Data may arrive in batches.")
        protocol.childDataReceived(0, b"Even when you least expect it.")
        self.assertEqual(protocol.get_data(), "Data may arrive in batches.")

    def test_restart_stops_exchanger(self):
        """
        After a successful shutdown, the broker stops processing new messages.
        """
        message = {"type": "shutdown", "reboot": False, "operation-id": 100}
        self.plugin.perform_shutdown(message)

        [arguments] = self.process_factory.spawns
        protocol = arguments[0]
        protocol.processEnded(Failure(ProcessDone(status=0)))
        self.broker_service.reactor.advance(100)
        self.manager.reactor.advance(100)

        # New messages will not be exchanged after a reboot process is in
        # process.
        self.manager.broker.exchanger.schedule_exchange()
        payloads = self.manager.broker.exchanger._transport.payloads
        self.assertEqual(0, len(payloads))
        return protocol.result
