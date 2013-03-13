import os
import json

from landscape.tests.helpers import LandscapeTest, ManagerHelper
from landscape.manager.cephusage import CephUsage


SAMPLE_TEMPLATE = ("   health HEALTH_WARN 6 pgs degraded; 6 pgs stuck "
"unclean\n"
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

SAMPLE_QUORUM = (''
'{ "election_epoch": 8,\n'
'  "quorum": [\n'
'        0,\n'
'        1,\n'
'        2],\n'
'  "monmap": { "epoch": 2,\n'
'      "fsid": "%s",\n'
'      "modified": "2013-01-13 16:58:00.141737",\n'
'      "created": "0.000000",\n'
'      "mons": [\n'
'            { "rank": 0,\n'
'              "name": "server-1be72d64-0ff2-4ac1-ad13-1c06c8201011",\n'
'              "addr": "10.55.60.188:6789\/0"},\n'
'            { "rank": 1,\n'
'              "name": "server-e847f147-ed13-46c2-8e6d-768aa32657ab",\n'
'              "addr": "10.55.60.202:6789\/0"},\n'
'            { "rank": 2,\n'
'              "name": "server-3c831a0b-51d5-43a9-95d5-63644f0965cc",\n'
'              "addr": "10.55.60.205:6789\/0"}]}}\n'
)

SAMPLE_QUORUM_OUTPUT = SAMPLE_QUORUM % "ecbb8960-0e21-11e2-b495-83a88f44db01"


class CephUsagePluginTest(LandscapeTest):
    helpers = [ManagerHelper]

    def setUp(self):
        super(CephUsagePluginTest, self).setUp()
        self.mstore = self.broker_service.message_store

    def test_get_ceph_usage_if_command_not_found(self):
        """
        When the ceph command cannot be found or accessed, the
        C{_get_ceph_usage} method returns None.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_none():
            return None

        plugin._get_ceph_command_output = return_none

        self.manager.add(plugin)

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

        self.manager.add(plugin)

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

        self.manager.add(plugin)

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

        self.manager.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertEqual(1.0, result)

    def test_get_ceph_usage_no_information(self):
        """
        When the ceph command outputs something that does not contain the
        disk usage information, the _get_ceph_usage method returns None.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return "Blah\nblah"

        plugin._get_ceph_command_output = return_output

        self.manager.add(plugin)

        result = plugin._get_ceph_usage()
        self.assertEqual(None, result)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty
        C{ceph-usages} list when no previous data is available.  If an empty
        message is created during exchange, it should not be queued.
        """
        self.mstore.set_accepted_types(["ceph-usage"])

        plugin = CephUsage(create_time=self.reactor.time)
        self.manager.add(plugin)

        self.manager.exchange()
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
        self.manager.add(plugin)

        self.manager.exchange()

        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "ceph-usage",
                              "ceph-usages": [(60, 1.0)],
                              "ring-id": ring_id}])

    def test_create_message(self):
        """
        Calling create_message returns an expected message.
        """
        plugin = CephUsage(create_time=self.reactor.time)
        self.manager.add(plugin)

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
        exchange_interval = 300

        plugin = CephUsage(create_time=self.reactor.time,
                          interval=interval, exchange_interval=300)

        self.manager.add(plugin)

        self.reactor.advance(exchange_interval * 2)
        self.manager.exchange()

        self.mstore.set_accepted_types(["ceph-usage"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_get_ceph_ring_id(self):
        """
        When given a well formatted command output, the _get_ceph_ring_id()
        method returns the correct ring_id.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        uuid = "i-am-a-uuid"

        def return_output():
            return SAMPLE_QUORUM % uuid

        plugin._get_quorum_command_output = return_output

        self.manager.add(plugin)

        result = plugin._get_ceph_ring_id()
        self.assertEqual(uuid, result)

    def test_get_ceph_ring_id_valid_json_no_information(self):
        """
        When the _get_quorum_command_output method returns something without
        the ring uuid information present but that is valid JSON, the
        _get_ceph_ring_id method returns None.
        """
        plugin = CephUsage(create_time=self.reactor.time)
        error = "Could not get ring_id from output: '{\"election_epoch\": 8}'."
        self.log_helper.ignore_errors(error)

        def return_output():
            # Valid JSON - just without the info we're looking for.
            data = {"election_epoch": 8}
            return json.dumps(data)

        plugin._get_quorum_command_output = return_output

        self.manager.add(plugin)

        result = plugin._get_ceph_ring_id()
        self.assertEqual(None, result)

    def test_get_ceph_ring_id_no_information(self):
        """
        When the _get_quorum_command_output method returns something without
        the ring uuid information present, the _get_ceph_ring_id method returns
        None.
        """
        plugin = CephUsage(create_time=self.reactor.time)
        error = "Could not get ring_id from output: 'Blah\nblah'."
        self.log_helper.ignore_errors(error)

        def return_output():
            return "Blah\nblah"

        plugin._get_quorum_command_output = return_output

        self.manager.add(plugin)

        result = plugin._get_ceph_ring_id()
        self.assertEqual(None, result)

    def test_plugin_run(self):
        """
        The plugin's run() method fills the _ceph_usage_points with
        accumulated samples after each C{interval} period.
        The _ceph_ring_id member of the plugin is also filled with the output
        of the _get_ceph_ring_id method.
        """
        exchange_interval = 300
        interval = exchange_interval
        plugin = CephUsage(create_time=self.reactor.time,
                           exchange_interval=exchange_interval,
                           interval=interval)
        uuid = "i-am-a-unique-snowflake"

        def return_quorum():
            return SAMPLE_QUORUM % uuid

        def return_full_disk():
            return SAMPLE_TEMPLATE % (100, 0, 100)

        plugin._ceph_config = "/etc/hosts"
        plugin._get_quorum_command_output = return_quorum
        plugin._get_ceph_command_output = return_full_disk

        self.manager.add(plugin)

        self.reactor.advance(exchange_interval * 2)

        self.assertEqual([(300, 1.0), (600, 1.0)], plugin._ceph_usage_points)
        self.assertEqual(uuid, plugin._ceph_ring_id)

    def test_flush_persists_data_to_disk(self):
        """
        The plugin's C{flush} method is called every C{flush_interval} and
        creates the perists file.
        """
        flush_interval = self.config.flush_interval
        persist_filename = os.path.join(self.config.data_path, "ceph.bpickle")

        self.assertFalse(os.path.exists(persist_filename))
        plugin = CephUsage(create_time=self.reactor.time)
        self.manager.add(plugin)

        self.reactor.advance(flush_interval)

        self.assertTrue(os.path.exists(persist_filename))

    def test_resynchronize_message_calls_resynchronize_method(self):
        """
        If the reactor fires a "resynchronize" even the C{_resynchronize}
        method on the ceph plugin object is called.
        """
        plugin = CephUsage(create_time=self.reactor.time)

        self.called = False

        def stub_resynchronize():
            self.called = True
        plugin._resynchronize = stub_resynchronize

        self.manager.add(plugin)

        self.reactor.fire("resynchronize")

        self.assertTrue(self.called)
