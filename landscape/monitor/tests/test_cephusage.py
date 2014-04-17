import os

from landscape.lib.fs import touch_file
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.monitor.cephusage import CephUsage


class CephUsagePluginTest(LandscapeTest):
    helpers = [MonitorHelper]

    def setUp(self):
        super(CephUsagePluginTest, self).setUp()
        self.mstore = self.broker_service.message_store
        self.plugin = CephUsage(create_time=self.reactor.time)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty
        C{ceph-usages} list when no previous data is available.  If an empty
        message is created during exchange, it should not be queued.
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

        self.plugin._ceph_usage_points = [(60, 1.0)]
        self.plugin._ceph_ring_id = ring_id
        self.monitor.add(self.plugin)

        self.monitor.exchange()
        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "ceph-usage",
                              "ceph-usages": [(60, 1.0)],
                              "ring-id": ring_id}])

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
        self.assertIn("ceph-usages", message)
        self.assertEqual(ring_id, message["ring-id"])
        ceph_usages = message["ceph-usages"]
        self.assertEqual(len(ceph_usages), 0)

        point = (60, 1.0)
        self.plugin._ceph_usage_points = [point]
        message = self.plugin.create_message()
        self.assertIn("type", message)
        self.assertEqual(message["type"], "ceph-usage")
        self.assertIn("ceph-usages", message)
        self.assertEqual(ring_id, message["ring-id"])
        ceph_usages = message["ceph-usages"]
        self.assertEqual(len(ceph_usages), 1)
        self.assertEqual([point], ceph_usages)

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

    def test_plugin_run(self):
        """
        The plugin's run() method fills the _ceph_usage_points with
        accumulated samples after each C{interval} period.
        The _ceph_ring_id member of the plugin is also filled with the output
        of the _get_ceph_ring_id method.
        """
        monitor_interval = 300
        interval = monitor_interval
        plugin = CephUsage(
            interval=interval, monitor_interval=monitor_interval,
            create_time=self.reactor.time)

        uuid = "i-am-a-unique-snowflake"
        stats = {"kb": 100, "kb_avail": 80}

        # The config file must be present for the plugin to run.
        ceph_client_dir = os.path.join(self.config.data_path, "ceph-client")
        ceph_conf = os.path.join(ceph_client_dir, "ceph.landscape-client.conf")
        os.mkdir(ceph_client_dir)
        touch_file(ceph_conf)

        plugin._ceph_config = ceph_conf

        # The rados library must be available for the plugin to run.
        plugin._has_rados = True

        plugin._perform_rados_call = lambda: (uuid, stats)

        self.monitor.add(plugin)

        self.reactor.advance(monitor_interval * 2)

        self.assertEqual([(300, 0.2), (600, 0.2)], plugin._ceph_usage_points)
        self.assertEqual(uuid, plugin._ceph_ring_id)

    def test_wb_get_ceph_usage(self):
        """
        The get_ceph_usage method returns a properly computed usage percentage
        and fsid.
        """
        uuid = u"unique"
        stats = {"kb": 100l, "kb_avail": 80l}

        plugin = CephUsage()

        fake_perform = lambda : (uuid, stats)

        result = plugin._get_ceph_usage(perform=fake_perform)
        expected = (uuid, 0.2)
        self.assertEqual(expected, result)

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
