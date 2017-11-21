import mock
from landscape.lib.fs import touch_file
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper
from landscape.client.monitor.cephusage import CephUsage


class CephUsagePluginTest(LandscapeTest):
    helpers = [MonitorHelper]

    def setUp(self):
        super(CephUsagePluginTest, self).setUp()
        self.mstore = self.broker_service.message_store
        self.plugin = CephUsage(create_time=self.reactor.time)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty C{data-points} list
        when no previous data is available.  If an empty message is created
        during exchange, it should not be queued.
        """
        self.mstore.set_accepted_types(["ceph-usage"])
        self.monitor.add(self.plugin)

        self.monitor.exchange()
        self.assertEqual(0, len(self.mstore.get_pending_messages()))

    def test_exchange_messages(self):
        """
        The Ceph usage plugin queues message when manager.exchange()
        is called.
        """
        ring_id = "whatever"
        self.mstore.set_accepted_types(["ceph-usage"])

        point = (60, 100000, 80000, 20000)
        self.plugin._ceph_usage_points = [point]
        self.plugin._ceph_ring_id = ring_id
        self.monitor.add(self.plugin)

        self.monitor.exchange()
        self.assertMessages(
            self.mstore.get_pending_messages(),
            [{"type": "ceph-usage",
              "ring-id": ring_id,
              "ceph-usages": [],
              "data-points": [point]}])

    def test_create_message(self):
        """
        Calling create_message returns an expected message.
        """
        ring_id = "blah"
        self.plugin._ceph_usage_points = []
        self.plugin._ceph_ring_id = ring_id
        message = self.plugin.create_message()

        self.assertIn("type", message)
        self.assertEqual(message["type"], "ceph-usage")
        self.assertIn("data-points", message)
        self.assertEqual(ring_id, message["ring-id"])
        data_points = message["data-points"]
        self.assertEqual(len(data_points), 0)

        point = (60, 100000, 80000, 20000)
        self.plugin._ceph_usage_points = [point]
        message = self.plugin.create_message()
        self.assertIn("type", message)
        self.assertEqual(message["type"], "ceph-usage")
        self.assertIn("data-points", message)
        self.assertEqual(ring_id, message["ring-id"])
        data_points = message["data-points"]
        self.assertEqual(len(data_points), 1)
        self.assertEqual([point], data_points)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently accepting
        their type.
        """
        interval = 30
        monitor_interval = 300

        plugin = CephUsage(
            interval=interval, monitor_interval=monitor_interval,
            create_time=self.reactor.time)

        self.monitor.add(plugin)

        self.reactor.advance(monitor_interval * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["ceph-usage"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_wb_should_run_inactive(self):
        """
        A plugin with self.active set to False should not run.
        """
        plugin = CephUsage()
        plugin.active = False
        self.assertFalse(plugin._should_run())

    def test_wb_should_run_no_config_file(self):
        """
        A plugin without a set _ceph_config attribute should not run.
        """
        plugin = CephUsage()
        plugin._has_rados = True
        plugin._ceph_config = None
        self.assertFalse(plugin._should_run())

    @mock.patch("logging.info")
    def test_wb_should_run_no_rados(self, logging):
        """
        If the Rados library cannot be imported (CephUsage._has_rados is False)
        the plugin logs a message then deactivates itself.
        """
        plugin = CephUsage()
        plugin._has_rados = False
        self.assertFalse(plugin._should_run())
        logging.assert_called_once_with(
            "This machine does not appear to be a Ceph machine. "
            "Deactivating plugin.")

    def test_wb_should_run(self):
        """
        If the Rados library is present with the correct version and a ceph
        config exists, the C{_should_run} method returns True.
        """
        plugin = CephUsage()
        plugin._has_rados = True
        plugin._ceph_config = self.makeFile()
        touch_file(plugin._ceph_config)
        self.assertTrue(plugin._should_run())

    def test_wb_handle_usage(self):
        """
        The C{_handle_usage} method stores the result of the rados call (here,
        an example value) in an Accumulator, and appends the step_data
        to the C{_ceph_usage_points} member when an accumulator interval is
        reached.
        """
        interval = 300
        stats = {"kb": 10240, "kb_avail": 8192, "kb_used": 2048}

        plugin = CephUsage(
            create_time=self.reactor.time, interval=interval,
            monitor_interval=interval)

        self.monitor.add(plugin)

        plugin._handle_usage(stats)  # time is 0

        self.reactor.advance(interval)  # time is 300
        plugin._handle_usage(stats)

        self.assertEqual(
            [(300, 10485760, 8388608, 2097152)], plugin._ceph_usage_points)

    def test_resynchronize_message_calls_reset_method(self):
        """
        If the reactor fires a "resynchronize" even the C{_reset}
        method on the ceph plugin object is called.
        """
        self.called = False

        def stub_reset():
            self.called = True

        self.plugin._reset = stub_reset
        self.monitor.add(self.plugin)
        self.reactor.fire("resynchronize")
        self.assertTrue(self.called)
