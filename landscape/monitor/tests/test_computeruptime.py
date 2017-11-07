from datetime import datetime
import struct

from landscape.monitor.computeruptime import (
        LoginInfo, LoginInfoReader, ComputerUptime, BootTimes)
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from mock import ANY, Mock


def append_login_data(filename, login_type=0, pid=0, tty_device="/dev/",
                      id="", username="", hostname="", termination_status=0,
                      exit_status=0, session_id=0, entry_time_seconds=0,
                      entry_time_milliseconds=0,
                      remote_ip_address=[0, 0, 0, 0]):
    """Append binary login data to the specified filename."""
    file = open(filename, "ab")
    try:
        file.write(struct.pack(LoginInfo.RAW_FORMAT, login_type, pid,
                               tty_device.encode("utf-8"), id.encode("utf-8"),
                               username.encode("utf-8"),
                               hostname.encode("utf-8"),
                               termination_status, exit_status, session_id,
                               entry_time_seconds, entry_time_milliseconds,
                               remote_ip_address[0], remote_ip_address[1],
                               remote_ip_address[2], remote_ip_address[3],
                               b""))
    finally:
        file.close()


class LoginInfoReaderTest(LandscapeTest):
    """Tests for login info file reader."""

    def test_read_empty_file(self):
        """Test ensures the reader is resilient to empty files."""
        filename = self.makeFile("")

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)
            self.assertEqual(reader.read_next(), None)
        finally:
            file.close()

    def test_read_login_info(self):
        """Test ensures the reader can read login info."""
        filename = self.makeFile("")
        append_login_data(filename, login_type=1, pid=100, tty_device="/dev/",
                          id="1", username="jkakar", hostname="localhost",
                          termination_status=0, exit_status=0, session_id=1,
                          entry_time_seconds=105, entry_time_milliseconds=10,
                          remote_ip_address=[192, 168, 42, 102])
        append_login_data(filename, login_type=1, pid=101, tty_device="/dev/",
                          id="1", username="root", hostname="localhost",
                          termination_status=0, exit_status=0, session_id=2,
                          entry_time_seconds=235, entry_time_milliseconds=17,
                          remote_ip_address=[192, 168, 42, 102])

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)

            info = reader.read_next()
            self.assertEqual(info.login_type, 1)
            self.assertEqual(info.pid, 100)
            self.assertEqual(info.tty_device, "/dev/")
            self.assertEqual(info.id, "1")
            self.assertEqual(info.username, "jkakar")
            self.assertEqual(info.hostname, "localhost")
            self.assertEqual(info.termination_status, 0)
            self.assertEqual(info.exit_status, 0)
            self.assertEqual(info.session_id, 1)
            self.assertEqual(info.entry_time, datetime.utcfromtimestamp(105))
            # FIXME Test IP address handling. -jk

            info = reader.read_next()
            self.assertEqual(info.login_type, 1)
            self.assertEqual(info.pid, 101)
            self.assertEqual(info.tty_device, "/dev/")
            self.assertEqual(info.id, "1")
            self.assertEqual(info.username, "root")
            self.assertEqual(info.hostname, "localhost")
            self.assertEqual(info.termination_status, 0)
            self.assertEqual(info.exit_status, 0)
            self.assertEqual(info.session_id, 2)
            self.assertEqual(info.entry_time, datetime.utcfromtimestamp(235))
            # FIXME Test IP address handling. -jk

            info = reader.read_next()
            self.assertEqual(info, None)
        finally:
            file.close()

    def test_login_info_iterator(self):
        """Test ensures iteration behaves correctly."""
        filename = self.makeFile("")
        append_login_data(filename)
        append_login_data(filename)

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)
            count = 0

            for info in reader.login_info():
                count += 1

            self.assertEqual(count, 2)
        finally:
            file.close()


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


class BootTimesTest(LandscapeTest):

    def test_fallback_to_uptime(self):
        """
        When no data is available in C{/var/log/wtmp}
        L{BootTimes.get_last_boot_time} falls back to C{/proc/uptime}.
        """
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)
        self.assertTrue(BootTimes(filename=wtmp_filename).get_last_boot_time())
