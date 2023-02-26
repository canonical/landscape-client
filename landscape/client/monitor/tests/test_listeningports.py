from unittest import mock

from landscape.client.monitor.listeningports import ListeningPorts
from landscape.client.tests.helpers import LandscapeTest
from landscape.client.tests.helpers import MonitorHelper
from landscape.lib.testing import LogKeeperHelper
from landscape.lib.tests.test_security import sample_listening_ports_canonical
from landscape.lib.tests.test_security import sample_subprocess_run


class ListeningPortsTest(LandscapeTest):
    """
    Tests relating to the L{ListeningPortsTes} monitoring plug-in, which should
    notice changes to listening ports and report these back to
    landscape server.
    """

    helpers = [MonitorHelper, LogKeeperHelper]

    def setUp(self):
        super().setUp()
        self.plugin = ListeningPorts()
        self.monitor.add(self.plugin)
        self.mstore.set_accepted_types(["listening-ports-info"])

    @mock.patch("landscape.lib.security.subprocess.run", sample_subprocess_run)
    def test_resynchronize(self):
        """
        The "resynchronize" reactor message cause the plugin to send fresh
        data.
        """
        self.plugin.run()
        self.reactor.fire("resynchronize", scopes=["security"])
        self.plugin.run()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)

    def test_run_interval(self):
        """
        The L{ListeningPorts} plugin will be scheduled to run every hour.
        """
        self.assertEqual(60, self.plugin.run_interval)

    def test_run_immediately(self):
        """
        The L{ListeningPorts} plugin will be run immediately at startup.
        """
        self.assertTrue(True, self.plugin.run_immediately)

    @mock.patch("landscape.lib.security.subprocess.run", sample_subprocess_run)
    def test_run(self):
        """
        If the server can accept them, the plugin should send
        C{listening-ports} messages.
        """
        with mock.patch.object(self.remote, "send_message"):
            self.plugin.run()
            self.remote.send_message.assert_called_once_with(
                mock.ANY,
                mock.ANY,
            )
        self.mstore.set_accepted_types([])
        self.plugin.run()

    @mock.patch("landscape.lib.security.subprocess.run", sample_subprocess_run)
    def test_send_message(self):
        """
        A new C{"listening-ports-info"} message should be enqueued if and only
        if the listening-ports status of the system has changed.
        """
        self.plugin.send_message()
        self.assertIn(
            "Queueing message with updated listening-ports status.",
            self.logfile.getvalue(),
        )
        canonical_sample = sample_listening_ports_canonical()
        self.assertMessages(
            self.mstore.get_pending_messages(),
            [{"type": "listening-ports-info", "ports": canonical_sample}],
        )
        self.mstore.delete_all_messages()
        self.plugin.send_message()
        self.assertMessages(
            self.mstore.get_pending_messages(),
            canonical_sample,
        )
