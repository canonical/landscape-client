from twisted.internet.defer import succeed

from landscape.monitor.swiftusage import SwiftUsage
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.tests.mocker import ANY


class FakeRing(object):
    def __init__(self, ip_port_tuples=[]):
        self.devs = [
            {"ip": ip, "port": port}
            for ip, port in ip_port_tuples]


MB = 1048576


class SwiftUsageTest(LandscapeTest):
    """Tests for swift-usage plugin."""

    helpers = [MonitorHelper]

    def setUp(self):
        LandscapeTest.setUp(self)
        self.mstore.set_accepted_types(["swift"])

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
        The swift_device_info plugin queues message when manager.exchange()
        is called.  Each message should be aligned to a step boundary;
        only a sing message with the latest swift device information will
        be delivered in a single message.
        """
        def perform_recon_call(host):
            return [
                {"device": "vdb",
                 "size": 100 * MB,
                 "used": 20 * MB,
                 "avail": 80 * MB,
                 "mounted": True}]

        plugin = SwiftUsage(
            create_time=self.reactor.time, swift_ring=self.makeFile("ring"))
        plugin._get_recon_host = ("192.168.1.10", 6000)
        plugin._has_swift = True
        plugin._perform_recon_call = perform_recon_call

        step_size = self.monitor.step_size
        self.monitor.add(plugin)

        # Exchange should trigger a flush of the persist database
        registry_mocker = self.mocker.replace(plugin.registry)
        registry_mocker.flush()
        self.mocker.result(None)
        self.mocker.replay()

        self.reactor.advance(step_size * 2)
        self.monitor.exchange()

        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        print messages
        # expected_message_content = [
        #         {"device": "/dev/hdf", "mounted": True},
        #         {"device": "/dev/hda2", "mounted": False}]

        # swift_devices = messages[0]["swift-device-info"]
        # self.assertEqual(swift_devices, expected_message_content)

    # def test_messaging_flushes(self):
    #     """
    #     Duplicate message should never be created.  If no data is
    #     available, None will be returned when messages are created.
    #     """
    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices

    #     self.reactor.advance(self.monitor.step_size)

    #     message = plugin.create_swift_device_info_message()
    #     self.assertEqual(message.keys(), ["swift-device-info", "type"])

    #     message = plugin.create_swift_device_info_message()
    #     self.assertEqual(message, None)

    # def test_never_exchange_empty_messages(self):
    #     """
    #     When the plugin has no data, its various create_X_message()
    #     methods will return None.  Empty or null messages should never
    #     be queued.
    #     """
    #     self.mstore.set_accepted_types(["load-average"])

    #     plugin = SwiftUsage()
    #     self.monitor.add(plugin)
    #     self.monitor.exchange()
    #     self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    # def test_messages_with_swift_data(self):
    #     """
    #     All swift-affiliated devices are sent in swift-device-info messages.
    #     Both mounted and unmounted swift devices send data.
    #     """
    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)

    #     plugin._get_swift_devices = fake_swift_devices

    #     step_size = self.monitor.step_size
    #     self.monitor.add(plugin)
    #     plugin.run()

    #     self.reactor.advance(step_size)
    #     self.monitor.exchange()

    #     messages = self.mstore.get_pending_messages()
    #     self.assertEqual(len(messages), 1)

    #     # Need to see both mounted and unmounted swift device info
    #     self.assertEqual(
    #         messages[0].get("swift-device-info"),
    #         [{'device': u'/dev/hdf', 'mounted': True},
    #          {'device': u'/dev/hda2', 'mounted': False}])

    # def test_resynchronize(self):
    #     """
    #     On the reactor "resynchronize" event, new swift-device-info messages
    #     should be sent.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time)

    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices

    #     plugin.run()
    #     plugin.exchange()
    #     self.reactor.fire("resynchronize", scopes=["storage"])
    #     plugin.run()
    #     plugin.exchange()
    #     messages = self.mstore.get_pending_messages()
    #     expected_message = {
    #         "type": "swift-device-info",
    #         "swift-device-info": [
    #             {"device": "/dev/hdf", "mounted": True},
    #             {"device": "/dev/hda2", "mounted": False}]}
    #     self.assertMessages(messages, [expected_message, expected_message])

    # def test_no_message_if_not_accepted(self):
    #     """
    #     Don't add any messages at all if the broker isn't currently
    #     accepting their type.
    #     """
    #     self.mstore.set_accepted_types([])

    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices

    #     self.reactor.advance(self.monitor.step_size * 2)
    #     self.monitor.exchange()

    #     self.mstore.set_accepted_types(["swift-device-info"])
    #     self.assertMessages(list(self.mstore.get_pending_messages()), [])

    # def test_call_on_accepted(self):
    #     """
    #     When message type acceptance is added for swift-device-info,
    #     send_message gets called.
    #     """
    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices

    #     self.reactor.advance(plugin.run_interval)

    #     remote_broker_mock = self.mocker.replace(self.remote)
    #     remote_broker_mock.send_message(ANY, ANY, urgent=True)
    #     self.mocker.result(succeed(None))
    #     self.mocker.count(1)  # 1 send message is called for swift-device-info
    #     self.mocker.replay()

    #     self.reactor.fire(
    #         ("message-type-acceptance-changed", "swift-device-info"), True)

    # def test_persist_deltas(self):
    #     """
    #     Swift persistent device info drops old devices from persist storage if
    #     the device no longer exists in the current device list.
    #     """
    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     def fake_swift_devices_no_hdf():
    #         return [{"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices
    #     plugin.run()
    #     plugin.exchange()  # To persist swift recon data
    #     self.assertEqual(
    #         plugin._persist.get("swift-device-info"),
    #         {"/dev/hdf": {"device": "/dev/hdf", "mounted": True},
    #          "/dev/hda2": {"device": "/dev/hda2", "mounted": False}})

    #     # Drop a device
    #     plugin._get_swift_devices = fake_swift_devices_no_hdf
    #     plugin.run()
    #     plugin.exchange()
    #     self.assertEqual(
    #         plugin._persist.get("swift-device-info"),
    #         {"/dev/hda2": {"device": "/dev/hda2", "mounted": False}})

    #     # Run again, calling create_swift_device_info_message which purges info
    #     plugin.run()
    #     plugin.exchange()
    #     message3 = plugin.create_swift_device_info_message()
    #     self.assertIdentical(message3, None)

    # def test_persist_timing(self):
    #     """Swift device info is only persisted when exchange happens.

    #     If an event happened between the persist and the exchange, the server
    #     didn't get the mount info at all. This test ensures that mount info are
    #     only saved when exchange happens.
    #     """
    #     def fake_swift_devices():
    #         return [{"device": "/dev/hdf", "mounted": True},
    #                 {"device": "/dev/hda2", "mounted": False}]

    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.monitor.add(plugin)
    #     plugin._get_swift_devices = fake_swift_devices
    #     plugin.run()
    #     message1 = plugin.create_swift_device_info_message()
    #     self.assertEqual(
    #         message1.get("swift-device-info"),
    #         [{"device": "/dev/hdf", "mounted": True},
    #          {"device": "/dev/hda2", "mounted": False}])
    #     plugin.run()
    #     message2 = plugin.create_swift_device_info_message()
    #     self.assertEqual(
    #         message2.get("swift-device-info"),
    #         [{"device": "/dev/hdf", "mounted": True},
    #          {"device": "/dev/hda2", "mounted": False}])
    #     # Run again, calling create_swift_device_info_message which purges info
    #     plugin.run()
    #     plugin.exchange()
    #     plugin.run()
    #     message3 = plugin.create_swift_device_info_message()
    #     self.assertIdentical(message3, None)

    # def test_wb_get_swift_devices_when_not_a_swift_node(self):
    #     """
    #     When not a swift node, _get_swift_devices returns an empty list and
    #     no error messages.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     self.assertEqual(plugin._get_swift_devices(), [])

    # def test_wb_get_swift_devices_when_on_a_swift_node(self):
    #     """
    #     When on a swift node, _get_swift_devices reports a warning if the ring
    #     files don't exist yet.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time,
    #                                  swift_config="/etc/hosts")
    #     logging_mock = self.mocker.replace("logging.warning")
    #     logging_mock("Swift ring files are not available yet.")
    #     self.mocker.replay()
    #     self.assertEqual(plugin._get_swift_devices(), [])

    # def test_run_disabled_when_missing_swift_config(self):
    #     """
    #     When on a node that doesn't have the appropriate swift config file. The
    #     plugin logs an info message and is disabled.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time,
    #                                  swift_config="/config/file/doesnotexist")
    #     logging_mock = self.mocker.replace("logging.info")
    #     logging_mock("This does not appear to be a swift storage server. "
    #                  "'swift-device-info' plugin has been disabled.")
    #     self.mocker.replay()
    #     self.monitor.add(plugin)
    #     self.assertEqual(plugin.enabled, True)
    #     plugin.run()
    #     self.assertEqual(plugin.enabled, False)

    # def test_wb_get_swift_devices_no_swift_python_libs_available(self):
    #     """
    #     The plugin logs an error and doesn't find swift devices when it can't
    #     import the swift python libs which it requires.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time,
    #                                  swift_config="/etc/hosts",
    #                                  swift_ring="/etc/hosts")

    #     logging_mock = self.mocker.replace("logging.error")
    #     logging_mock("Swift python common libraries not found. "
    #                  "'swift-device-info' plugin has been disabled.")
    #     self.mocker.replay()

    #     self.assertEqual(plugin._get_swift_devices(), [])

    # def test_wb_get_swift_disk_usage_when_no_swift_service_running(self):
    #     """
    #     When the swift service is running, but recon middleware is not active,
    #     the Swift storage usage logs an error.
    #     """
    #     self.log_helper.ignore_errors(".*")
    #     plugin = SwiftUsage(create_time=self.reactor.time)
    #     plugin._swift_recon_url = "http://localhost:12654"
    #     result = plugin._get_swift_disk_usage()
    #     self.assertIs(None, result)
    #     self.assertIn(
    #         "Swift service not available at %s." % plugin._swift_recon_url,
    #         self.logfile.getvalue())

    # def test_wb_get_swift_disk_usage_when_no_recon_service_configured(self):
    #     """
    #     When the swift service is running, but recon middleware is not active,
    #     an error is logged.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time)

    #     plugin._swift_recon_url = "http://localhost:12654"

    #     def fetch_error(url):
    #         raise HTTPCodeError(400, "invalid path: /recon/diskusage")
    #     plugin._fetch = fetch_error

    #     logging_mock = self.mocker.replace("logging.error", passthrough=False)
    #     logging_mock(
    #         "Swift service is running without swift-recon enabled. "
    #         "'swift-device-info' plugin has been disabled.")
    #     self.mocker.result(None)
    #     self.mocker.replay()

    #     result = plugin._get_swift_disk_usage()
    #     self.assertIs(None, result)

    # def test_wb_get_swift_usage_no_information(self):
    #     """
    #     When the swift recon service returns no disk usage information,
    #     the _get_swift_disk_usage method returns None.
    #     """
    #     plugin = SwiftUsage(create_time=self.reactor.time)

    #     def fetch_none(url):
    #         return None

    #     plugin._fetch = fetch_none

    #     result = plugin._get_swift_disk_usage()
    #     self.assertEqual(None, result)

    # def test_wb_get_swift_devices_no_matched_local_service(self):
    #     """
    #     The plugin logs an error when the swift ring file does not represent
    #     a swift service running local IP address on the current node.
    #     """
    #     plugin = SwiftUsage(
    #         create_time=self.reactor.time, swift_config="/etc/hosts")

    #     def get_fake_ring():
    #         return FakeRingInfo([("192.168.1.10", 6000)])
    #     plugin._get_ring = get_fake_ring

    #     def local_network_devices():
    #         return [{"ip_address": "10.1.2.3"}]
    #     plugin._get_network_devices = local_network_devices

    #     logging_mock = self.mocker.replace("logging.error")
    #     logging_mock("Local swift service not found. "
    #                  "'swift-device-info' plugin has been disabled.")
    #     self.mocker.replay()
    #     self.assertEqual(plugin._get_swift_devices(), [])
