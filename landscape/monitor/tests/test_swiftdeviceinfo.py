import tempfile

from twisted.internet.defer import succeed

from landscape.lib.fetch import HTTPCodeError
from landscape.monitor.swiftdeviceinfo import SwiftDeviceInfo
from landscape.tests.test_hal import MockHALManager, MockRealHALDevice
from landscape.tests.helpers import LandscapeTest, mock_counter, MonitorHelper
from landscape.tests.mocker import ANY


mb = lambda x: x * 1024 * 1024


class FakeRingInfo(object):
    def __init__(self, ip_port_tuples=[]):
        self.devs = []
        for ip, port in ip_port_tuples:
            self.devs.append({"ip": ip, "port": port})


class SwiftDeviceInfoTest(LandscapeTest):
    """Tests for swift-device-info plugin."""

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.mstore.set_accepted_types(["swift-device-info"])

    def test_exchange_messages(self):
        """
        The swift_device_info plugin queues message when manager.exchange()
        is called.  Each message should be aligned to a step boundary;
        messages collected between exchange periods should be
        delivered in a single message.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)

        step_size = self.monitor.step_size
        self.monitor.add(plugin)

        # Exchange should trigger a flush of the persist database
        registry_mocker = self.mocker.replace(plugin.registry)
        registry_mocker.flush()
        self.mocker.result(None)
        self.mocker.replay()

        import pdb;pdb.set_trace()
        self.reactor.advance(step_size * 2)
        self.monitor.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)

        message = [d for d in messages if d["type"] == "free-space"][0]
        free_space = message["free-space"]
        for i in range(len(free_space)):
            self.assertEqual(free_space[i][0], (i + 1) * step_size)
            self.assertEqual(free_space[i][1], "/")
            self.assertEqual(free_space[i][2], 409600)

    def test_messaging_flushes(self):
        """
        Duplicate message should never be created.  If no data is
        available, None will be returned when messages are created.
        """
        def statvfs(path):
            return (4096, 0, mb(1000), mb(100), 0, 0, 0, 0, 0)

        filename = self.makeFile("""\
/dev/hda1 / ext3 rw 0 0
""")
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size)

        messages = plugin.create_swift_device_info_message()
        self.assertEqual(len(messages), 2)

        messages = plugin.create_messages()
        self.assertEqual(len(messages), 0)

    def test_never_exchange_empty_messages(self):
        """
        When the plugin has no data, it's various create_X_message()
        methods will return None.  Empty or null messages should never
        be queued.
        """
        self.mstore.set_accepted_types(["load-average"])

        filename = self.makeFile("")
        plugin = SwiftDeviceInfo()
        self.monitor.add(plugin)
        self.monitor.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    def test_messages(self):
        """
        Test ensures all expected messages are created and contain the
        right datatypes.
        """
        def statvfs(path):
            return (4096, 0, mb(1000), mb(100), 0, 0, 0, 0, 0)

        filename = self.makeFile("""\
/dev/hda2 / xfs rw 0 0
""")
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        step_size = self.monitor.step_size
        self.monitor.add(plugin)

        self.reactor.advance(step_size)
        self.monitor.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].get("mount-info"),
                         [(step_size,
                           {"device": "/dev/hda2", "mount-point": "/",
                            "filesystem": "xfs", "total-space": 4096000})])
        self.assertEqual(messages[1].get("free-space"),
                         [(step_size, "/", 409600)])
        self.assertTrue(isinstance(messages[1]["free-space"][0][2],
                                   (int, long)))

    def test_messages_with_swift_data(self):
        """
        All swift-affiliated devices are sent in swift-device-info messages.
        """
        def fake_swift_devices():
            return [{"device": "/dev/hdf", "mounted": True},
                    {"device": "/dev/hda2", "mounted": False}]

        plugin = SwiftDeviceInfo(create_time=self.reactor.time)

        plugin._get_swift_devices = fake_swift_devices

        step_size = self.monitor.step_size
        self.monitor.add(plugin)
        plugin.run()

        self.reactor.advance(step_size)
        self.monitor.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

        # Need to see both mounted and unmounted swift device info
        self.assertEqual(
            messages[0].get("swift-device-info"),
            [{'device': u'/dev/hdf', 'mounted': True},
             {'device': u'/dev/hda2', 'mounted': False}])

    def test_resynchronize(self):
        """
        On the reactor "resynchronize" event, new swift-device-info messages
        should be sent.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        def fake_swift_devices():
            return [{"device": "/dev/hdf", "mounted": True},
                    {"device": "/dev/hda2", "mounted": False}]

        self.monitor.add(plugin)
        plugin._get_swift_devices = fake_swift_devices

        plugin.run()
        plugin.exchange()
        self.reactor.fire("resynchronize")
        plugin.run()
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        expected_message = {
            "type": "swift-device-info",
            "swift-device-info": [
                {"device": "/dev/hdf", "mounted": True},
                {"device": "/dev/hda2", "mounted": False}]}
        self.assertMessages(messages, [expected_message, expected_message])

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        self.mstore.set_accepted_types([])

        def fake_swift_devices():
            return [{"device": "/dev/hdf", "mounted": True},
                    {"device": "/dev/hda2", "mounted": False}]

        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)
        plugin._get_swift_devices = fake_swift_devices

        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["swift-device-info"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_call_on_accepted(self):
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(plugin.run_interval)

        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, urgent=True)
        self.mocker.result(succeed(None))
        self.mocker.count(2)
        self.mocker.replay()

        self.reactor.fire(("message-type-acceptance-changed", "swift-device-info"),
                          True)

    def test_persist_timing(self):
        """Mount info are only persisted when exchange happens.

        Previously mount info were persisted as soon as they were gathered: if
        an event happened between the persist and the exchange, the server
        didn't get the mount info at all. This test ensures that mount info are
        only saved when exchange happens.
        """
        def statvfs(path):
            return (4096, 0, mb(1000), mb(100), 0, 0, 0, 0, 0)

        filename = self.makeFile("""\
/dev/hda1 / ext3 rw 0 0
""")
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)
        plugin.run()
        message1 = plugin.create_mount_info_message()
        self.assertEqual(
            message1.get("mount-info"),
            [(0, {"device": "/dev/hda1",
                  "filesystem": "ext3",
                  "mount-point": "/",
                  "total-space": 4096000L})])
        plugin.run()
        message2 = plugin.create_mount_info_message()
        self.assertEqual(
            message2.get("mount-info"),
            [(0, {"device": "/dev/hda1",
                  "filesystem": "ext3",
                  "mount-point": "/",
                  "total-space": 4096000L})])
        # Run again, calling create_mount_info_message purge the information
        plugin.run()
        plugin.exchange()
        plugin.run()
        message3 = plugin.create_mount_info_message()
        self.assertIdentical(message3, None)

    def test_wb_get_swift_devices_when_not_a_swift_node(self):
        """
        When not a swift node, _get_swift_devices returns an empty list and
        no error messages.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)
        self.assertEqual(plugin._get_swift_devices(), [])

    def test_wb_get_swift_devices_when_on_a_swift_node(self):
        """
        When on a swift node, _get_swift_devices reports a warning if the ring
        files don't exist yet.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time,
                                     swift_config="/etc/hosts")
        logging_mock = self.mocker.replace("logging.warning")
        logging_mock("Swift ring files are not available yet.")
        self.mocker.replay()
        self.assertEqual(plugin._get_swift_devices(), [])

    def test_wb_get_swift_devices_no_swift_python_libs_available(self):
        """
        The plugin logs an error and doesn't find swift devices when it can't
        import the swift python libs which it requires.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time,
                                     swift_config="/etc/hosts",
                                     swift_ring="/etc/hosts")

        logging_mock = self.mocker.replace("logging.error")
        logging_mock("Swift python common libraries not found.")
        self.mocker.replay()

        self.assertEqual(plugin._get_swift_devices(), [])

    def test_wb_get_swift_disk_usage_when_no_swift_service_running(self):
        """
        When the swift service is running, but recon middleware is not active,
        the Swift storage usage logs an error.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)

        plugin._swift_recon_url = "http://localhost:12654"

        logging_mock = self.mocker.replace("logging.error")
        logging_mock(
            "Swift service not available at %s. "
            "Error 7: couldn't connect to host" %
                     plugin._swift_recon_url)
        self.mocker.result(None)
        self.mocker.replay()

        result = plugin._get_swift_disk_usage()
        self.assertIs(None, result)

    def test_wb_get_swift_disk_usage_when_no_recon_service_configured(self):
        """
        When the swift service is running, but recon middleware is not active,
        an error is logged.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)

        plugin._swift_recon_url = "http://localhost:12654"

        def fetch_error(url):
            raise HTTPCodeError(400, "invalid path: /recon/diskusage")
        plugin._fetch = fetch_error

        logging_mock = self.mocker.replace("logging.error", passthrough=False)
        logging_mock(
            "Swift service is running without swift-recon enabled.")
        self.mocker.result(None)
        self.mocker.replay()

        result = plugin._get_swift_disk_usage()
        self.assertIs(None, result)

    def test_wb_get_swift_usage_no_information(self):
        """
        When the swift recon service returns no disk usage information,
        the _get_swift_disk_usage method returns None.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time)

        def fetch_none(url):
            return None

        plugin._fetch = fetch_none

        result = plugin._get_swift_disk_usage()
        self.assertEqual(None, result)

    def test_wb_get_swift_devices_no_matched_local_service(self):
        """
        The plugin logs an error when the swift ring file does not represent
        a swift service running local IP address on the current node.
        """
        plugin = SwiftDeviceInfo(create_time=self.reactor.time,
                                     swift_config="/etc/hosts")

        def get_fake_ring():
            return FakeRingInfo([("192.168.1.10", 6000)])
        plugin._get_ring = get_fake_ring

        def local_network_devices():
            return [{"ip_address": "10.1.2.3"}]
        plugin._get_network_devices = local_network_devices

        logging_mock = self.mocker.replace("logging.error")
        logging_mock("Local swift service not found.")
        self.mocker.replay()
        self.assertEqual(plugin._get_swift_devices(), [])
