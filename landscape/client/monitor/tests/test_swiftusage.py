from twisted.internet.defer import succeed
from unittest import skipUnless

from landscape.client.monitor.swiftusage import SwiftUsage
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from mock import ANY, Mock

try:
    from swift.cli.recon import Scout
    has_swift = True
except ImportError:
    has_swift = False


class FakeRing(object):
    def __init__(self, ip_port_tuples=[]):
        self.devs = [
            {"ip": ip, "port": port}
            for ip, port in ip_port_tuples]


class SwiftUsageTest(LandscapeTest):
    """Tests for swift-usage plugin."""

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.mstore.set_accepted_types(["swift-usage"])
        self.plugin = SwiftUsage(
            create_time=self.reactor.time, swift_ring=self.makeFile("ring"))
        self.plugin._has_swift = True

    def test_wb_should_run_not_active(self):
        """
        L{SwiftUsage._should_run} returns C{False} if plugin is not active.
        """
        plugin = SwiftUsage(create_time=self.reactor.time)
        plugin.active = False
        self.assertFalse(plugin._should_run())

    def test_wb_should_run_no_swift(self):
        """
        L{SwiftUsage._should_run} returns C{False} if Swift client library is
        not available. It also disables the plugin.
        """
        plugin = SwiftUsage(create_time=self.reactor.time)
        plugin._has_swift = False
        self.assertFalse(plugin._should_run())
        self.assertFalse(plugin.active)

    def test_wb_should_run_no_swift_ring(self):
        """
        L{SwiftUsage._should_run} returns C{False} if Swift ring configuration
        file is not found.
        """
        plugin = SwiftUsage(
            create_time=self.reactor.time, swift_ring=self.makeFile())
        plugin._has_swift = True
        self.assertFalse(plugin._should_run())

    def test_wb_should_run(self):
        """
        L{SwiftUsage._should_run} returns C{True} if everything if the Swift
        ring is properly configured.
        """
        plugin = SwiftUsage(
            create_time=self.reactor.time, swift_ring=self.makeFile("ring"))
        plugin._has_swift = True
        self.assertTrue(plugin._should_run())

    def test_exchange_messages(self):
        """
        The plugin queues message when manager.exchange() is called.
        Each message should be aligned to a step boundary; only a sing message
        with the latest swift device information will be delivered in a single
        message.
        """
        points = [(1234, "sdb", 100000, 80000, 20000),
                  (1234, "sdc", 200000, 120000, 800000)]
        self.plugin._swift_usage_points = points

        self.monitor.add(self.plugin)
        self.monitor.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        data_points = messages[0]["data-points"]
        self.assertEqual(points, data_points)

    def test_no_exchange_empty_messages(self):
        """
        If no usage data is available, no message is exchanged.
        """
        self.monitor.add(self.plugin)
        self.monitor.exchange()

        self.assertEqual([], self.mstore.get_pending_messages())

    def test_create_message(self):
        """L{SwiftUsage.create_message} returns a 'swift-usage' message."""
        points = [(1234, "sdb", 100000, 80000, 20000),
                  (1234, "sdc", 200000, 120000, 80000)]
        self.plugin._swift_usage_points = points
        message = self.plugin.create_message()
        self.assertEqual(
            {"type": "swift-usage", "data-points": points}, message)

    def test_create_message_empty(self):
        """
        L{SwiftUsage.create_message} returns C{None} if no data are available.
        """
        self.assertIs(None, self.plugin.create_message())

    def test_crate_message_flushes(self):
        """Duplicate message should never be created."""
        self.monitor.add(self.plugin)
        self.plugin._swift_usage_points = [(1234, "sdb", 100000, 80000, 20000)]
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.reactor.advance(self.monitor.step_size)
        message = self.plugin.create_message()
        self.assertIsNot(None, message)
        message = self.plugin.create_message()
        self.assertIs(None, message)

    def test_no_message_if_not_accepted(self):
        """
        No message is sent if the broker isn't currently accepting their type.
        """
        self.plugin._swift_usage_points = [(1234, "sdb", 100000, 80000, 20000)]
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.mstore.set_accepted_types([])
        self.monitor.add(self.plugin)

        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_call_on_accepted(self):
        """
        When message type acceptance is added for 'swift' message,
        send_message gets called.
        """
        self.plugin._swift_usage_points = [(1234, "sdb", 100000, 80000, 20000)]
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.monitor.add(self.plugin)
        self.reactor.advance(self.plugin.run_interval)

        self.remote.send_message = Mock(return_value=succeed(None))
        self.reactor.fire(
            ("message-type-acceptance-changed", "swift-usage"), True)
        self.remote.send_message.assert_called_once_with(ANY, ANY, urgent=True)

    def test_message_only_mounted_devices(self):
        """
        The plugin only collects usage for mounted devices.
        """
        recon_response = [
            {"device": "vdb",
             "mounted": True,
             "size": 100000,
             "avail": 80000,
             "used": 20000},
            {"device": "vdc",
             "mounted": False,
             "size": "",
             "avail": "",
             "used": ""},
            {"device": "vdd",
             "mounted": True,
             "size": 200000,
             "avail": 10000,
             "used": 190000}]
        self.plugin._perform_recon_call = lambda host: succeed(recon_response)
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.monitor.add(self.plugin)
        self.reactor.advance(self.plugin._interval)
        self.plugin._handle_usage(recon_response)

        self.assertEqual(
            [(30, "vdb", 100000, 80000, 20000),
             (30, "vdd", 200000, 10000, 190000)],
            self.plugin._swift_usage_points)
        self.assertEqual(
            ["vdb", "vdd"], sorted(self.plugin._persist.get("devices")))
        self.assertNotIn("vdc", self.plugin._persist.get("usage"))

    def test_message_remove_disappeared_devices(self):
        """
        Usage for devices that have disappeared are removed from the persist.
        """
        recon_response = [
            {"device": "vdb",
             "mounted": True,
             "size": 100000,
             "avail": 80000,
             "used": 20000},
            {"device": "vdc",
             "mounted": True,
             "size": 200000,
             "avail": 10000,
             "used": 190000}]
        self.plugin._perform_recon_call = lambda host: succeed(recon_response)
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.monitor.add(self.plugin)
        self.reactor.advance(self.monitor.step_size)
        self.plugin._handle_usage(recon_response)
        self.assertEqual(
            ["vdb", "vdc"], sorted(self.plugin._persist.get("devices")))

        recon_response = [
            {"device": "vdb",
             "mounted": True,
             "size": 100000,
             "avail": 70000,
             "used": 30000}]
        self.reactor.advance(self.monitor.step_size)
        self.plugin._handle_usage(recon_response)
        self.assertNotIn("vdc", self.plugin._persist.get("usage"))
        self.assertEqual(["vdb"], self.plugin._persist.get("devices"))

    def test_message_remove_unmounted_devices(self):
        """
        Usage for devices that are no longer mounted are removed from the
        persist.
        """
        recon_response = [
            {"device": "vdb",
             "mounted": True,
             "size": 100000,
             "avail": 80000,
             "used": 20000},
            {"device": "vdc",
             "mounted": True,
             "size": 200000,
             "avail": 10000,
             "used": 190000}]
        self.plugin._perform_recon_call = lambda host: succeed(recon_response)
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.monitor.add(self.plugin)
        self.reactor.advance(self.monitor.step_size)
        self.plugin._handle_usage(recon_response)
        self.assertEqual(
            ["vdb", "vdc"], sorted(self.plugin._persist.get("devices")))

        recon_response = [
            {"device": "vdb",
             "mounted": True,
             "size": 100000,
             "avail": 70000,
             "used": 30000},
            {"device": "vdc",
             "mounted": False,
             "size": "",
             "avail": "",
             "used": ""}]
        self.reactor.advance(self.monitor.step_size)
        self.plugin._handle_usage(recon_response)
        self.assertNotIn("vdc", self.plugin._persist.get("usage"))
        self.assertEqual(["vdb"], self.plugin._persist.get("devices"))

    @skipUnless(has_swift, "Test relies on python-swift being installed")
    def test_perform_recon_call(self):
        """
        Checks that disk usage is correctly returned after the change
        in scout() results
        """
        plugin = SwiftUsage(create_time=self.reactor.time)
        expected_disk_usage = [
            {u"device": u"vdb",
             u"mounted": True,
             u"size": 100000,
             u"avail": 70000,
             u"used": 30000}]
        Scout.scout = lambda _, host: ("recon_url", expected_disk_usage, 200,
                                       1459286522.711885, 1459286522.716989)
        host = ("192.168.1.10", 6000)
        response = plugin._perform_recon_call(host)
        self.assertEqual(response, expected_disk_usage)

    @skipUnless(has_swift, "Test relies on python-swift being installed")
    def test_perform_old_recon_call(self):
        """
        Checks that disk usage is correctly returned with the old scout()
        result format as well
        """
        plugin = SwiftUsage(create_time=self.reactor.time)
        expected_disk_usage = [
            {u"device": u"vdb",
             u"mounted": True,
             u"size": 100000,
             u"avail": 70000,
             u"used": 30000}]
        Scout.scout = lambda _, host: ("recon_url", expected_disk_usage, 200)
        host = ("192.168.1.10", 6000)
        response = plugin._perform_recon_call(host)
        self.assertEqual(response, expected_disk_usage)

    def test_device_enconding(self):
        """
        Checks that unicode responses can be processed without errors
        """
        recon_response = [
            {u"device": u"vdb",
             u"mounted": True,
             u"size": 100000,
             u"avail": 70000,
             u"used": 30000}]
        self.plugin._perform_recon_call = lambda host: succeed(recon_response)
        self.plugin._get_recon_host = lambda: ("192.168.1.10", 6000)

        self.monitor.add(self.plugin)
        self.reactor.advance(self.monitor.step_size)
        self.plugin._handle_usage(recon_response)
        self.assertEqual(
            [u"vdb"], sorted(self.plugin._persist.get("devices")))

    def test_wb_handle_usage_with_invalid_data(self):
        """Checks that _handle_usage does not raise with invalid recon data.

        This should cover the case where the monitor is started while the
        swift unit is not yet active. The plugin should stay active, and not
        raise uncaught errors as it would stop the run loop from running
        again.
        """
        # Expects a list, but can get None if there is an error.
        self.plugin._handle_usage(None)
        self.assertTrue(self.plugin.active)
