from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.monitor.ceph import CephUsage


SAMPLE_TEMPLATE = ("   health HEALTH_WARN 6 pgs degraded; 6 pgs stuck unclean\n"
"monmap e2: 3 mons at {server-269703f4-5217-495a-b7f2-b3b3473c1719="
"10.55.60.238:6789/0,server-3f370698-f3b0-4cbe-8db9-a18e304c952b="
"10.55.60.141:6789/0,server-f635fa07-e36f-453c-b3d5-b4ce86fbc6ff="
"10.55.60.241:6789/0}, election epoch 8, quorum 0,1,2 "
"server-269703f4-5217-495a-b7f2-b3b3473c1719,"
"server-3f370698-f3b0-4cbe-8db9-a18e304c952b,"
"server-f635fa07-e36f-453c-b3d5-b4ce86fbc6ff\n   "
"osdmap e9: 3 osds: 3 up, 3 in\n    "
"pgmap v114: 192 pgs: 186 active+clean, 6 active+degraded; "
"0 bytes data, %s MB used, %s MB / %s MB avail\n   "
"mdsmap e1: 0/0/1 up\n\n")

SAMPLE_OUTPUT = SAMPLE_TEMPLATE % (4296, 53880, 61248)


class CephUsagePluginTest(LandscapeTest):
    helpers = [MonitorHelper]

    def test_get_ceph_usage_if_command_not_found(self):
        """
        When the ceph command cannot be found or accessed, the
        C{_get_ceph_usage} method returns None.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_none():
            return None

        plugin._get_ceph_command_output = return_none

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertIs(None, result)

    def test_get_ceph_usage(self):
        """
        When the ceph command call returns output, the _get_ceph_usage method
        returns the percentage of used space.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_OUTPUT

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertEqual(0.12029780564263323, result)

    def test_get_ceph_usage_empty_disk(self):
        """
        When the ceph command call returns output for empty disks, the
        _get_ceph_usage method returns 0.0 .
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_TEMPLATE % (0, 100, 100)

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertEqual(0.0, result)

    def test_get_ceph_usage_full_disk(self):
        """
        When the ceph command call returns output for empty disks, the
        _get_ceph_usage method returns 1.0 .
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_TEMPLATE % (100, 0, 100)

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertEqual(1.0, result)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty
        C{ceph-usages} list when no previous data is available.  If an empty
        message is created during exchange, it should not be queued.
        """
        self.mstore.set_accepted_types(["ceph-usage"])

        plugin = CephUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.monitor.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    def test_exchange_messages(self):
        """
        The Ceph usage plugin queues message when manager.exchange()
        is called.
        """
        ring_id = "whatever"
        self.mstore.set_accepted_types(["ceph-usage"])

        plugin = CephUsage(create_time=self.reactor.time)
        plugin._ceph_usage_points = [(60, 1.0)]
        plugin._ceph_ring_id = ring_id
        self.monitor.add(plugin)

        self.monitor.exchange()

        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "ceph-usage",
                              "ceph-usages": [(60, 1.0)],
                              "ring-id": ring_id}])

    def test_create_message(self):
        """
        Calling create_message returns an expected message.
        """
        plugin = CephUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        ring_id = "blah"
        plugin._ceph_usage_points = []
        plugin._ceph_ring_id = ring_id
        message = plugin.create_message()

        self.assertIn("type", message)
        self.assertEqual(message["type"], "ceph-usage")
        self.assertIn("ceph-usages", message)
        self.assertEqual(ring_id, message["ring-id"])
        ceph_usages = message["ceph-usages"]
        self.assertEqual(len(ceph_usages), 0)

        point = (60, 1.0)
        plugin._ceph_usage_points = [point]
        message = plugin.create_message()
        self.assertIn("type", message)
        self.assertEqual(message["type"], "ceph-usage")
        self.assertIn("ceph-usages", message)
        self.assertEqual(ring_id, message["ring-id"])
        ceph_usages = message["ceph-usages"]
        self.assertEqual(len(ceph_usages), 1)
        self.assertEqual([point], ceph_usages)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        interval = 30

        plugin = CephUsage(create_time=self.reactor.time,
                          interval=interval)

        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["ceph-usage"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])
