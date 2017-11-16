from landscape.lib.testing import append_login_data
from landscape.client.monitor.computeruptime import ComputerUptime
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from mock import ANY, Mock


class ComputerUptimeTest(LandscapeTest):
    """Tests for the computer-uptime plugin."""

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.mstore.set_accepted_types(["computer-uptime"])

    def test_deliver_message(self):
        """Test delivering a message with the boot and shutdown times."""
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)
        plugin.run()

        message = self.mstore.get_pending_messages()[0]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [535])

    def test_only_deliver_unique_shutdown_messages(self):
        """Test that only unique shutdown messages are generated."""
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)

        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)

        plugin.run()
        message = self.mstore.get_pending_messages()[0]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [535])

        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=3212)

        plugin.run()
        message = self.mstore.get_pending_messages()[1]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [3212])

    def test_only_queue_messages_with_data(self):
        """Test ensures that messages without data are not queued."""
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=3212)
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=3562)
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)

        plugin.run()
        self.assertEqual(len(self.mstore.get_pending_messages()), 1)

        plugin.run()
        self.assertEqual(len(self.mstore.get_pending_messages()), 1)

    def test_missing_wtmp_file(self):
        wtmp_filename = self.makeFile()
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)
        plugin.run()
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    def test_boot_time_same_as_last_known_startup_time(self):
        """Ensure one message is queued for duplicate startup times."""
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=3212)
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)
        plugin.run()
        plugin.run()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "computer-uptime")
        self.assertEqual(messages[0]["startup-times"], [3212])

    def test_new_startup_time_replaces_old_startup_time(self):
        """
        Test ensures startup times are not duplicated even across restarts of
        the client. This is simulated by creating a new instance of the plugin.
        """
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=3212)
        plugin1 = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin1)
        plugin1.run()

        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=3871)
        append_login_data(wtmp_filename, tty_device="~", username="reboot",
                          entry_time_seconds=4657)
        plugin2 = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin2)
        plugin2.run()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["type"], "computer-uptime")
        self.assertEqual(messages[0]["startup-times"], [3212])
        self.assertEqual(messages[1]["type"], "computer-uptime")
        self.assertEqual(messages[1]["startup-times"], [4657])

    def test_check_last_logrotated_file(self):
        """Test ensures reading falls back to logrotated files."""
        wtmp_filename = self.makeFile("")
        logrotated_filename = self.makeFile("", path=wtmp_filename + ".1")
        append_login_data(logrotated_filename, tty_device="~",
                          username="reboot", entry_time_seconds=125)
        append_login_data(logrotated_filename, tty_device="~",
                          username="shutdown", entry_time_seconds=535)

        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)

        plugin.run()
        message = self.mstore.get_pending_messages()[0]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("startup-times" in message)
        self.assertEqual(message["startup-times"], [125])
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [535])

    def test_check_logrotate_spillover(self):
        """Test ensures reading falls back to logrotated files."""
        wtmp_filename = self.makeFile("")
        logrotated_filename = self.makeFile("", path=wtmp_filename + ".1")
        append_login_data(logrotated_filename, tty_device="~",
                          username="reboot", entry_time_seconds=125)
        append_login_data(logrotated_filename, tty_device="~",
                          username="shutdown", entry_time_seconds=535)
        append_login_data(wtmp_filename, tty_device="~",
                          username="reboot", entry_time_seconds=1025)
        append_login_data(wtmp_filename, tty_device="~",
                          username="shutdown", entry_time_seconds=1150)

        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)

        plugin.run()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)

        message = messages[0]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("startup-times" in message)
        self.assertEqual(message["startup-times"], [125])
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [535])

        message = messages[1]
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "computer-uptime")
        self.assertTrue("startup-times" in message)
        self.assertEqual(message["startup-times"], [1025])
        self.assertTrue("shutdown-times" in message)
        self.assertEqual(message["shutdown-times"], [1150])

    def test_call_on_accepted(self):
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)

        self.remote.send_message = Mock()

        self.reactor.fire(("message-type-acceptance-changed",
                           "computer-uptime"),
                          True)
        self.remote.send_message.assert_called_once_with(ANY, ANY, urgent=True)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        self.mstore.set_accepted_types([])
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)
        plugin = ComputerUptime(wtmp_file=wtmp_filename)
        self.monitor.add(plugin)
        plugin.run()
        self.mstore.set_accepted_types(["computer-uptime"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])
