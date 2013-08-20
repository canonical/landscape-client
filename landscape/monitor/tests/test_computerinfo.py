import os
import re

from twisted.internet.defer import succeed, fail

from landscape.lib.fetch import HTTPCodeError, FetchError
from landscape.lib.fs import create_file
from landscape.monitor.computerinfo import ComputerInfo
from landscape.tests.helpers import LandscapeTest, MonitorHelper
from landscape.tests.mocker import ANY

SAMPLE_LSB_RELEASE = "DISTRIB_ID=Ubuntu\n"                         \
                     "DISTRIB_RELEASE=6.06\n"                      \
                     "DISTRIB_CODENAME=dapper\n"                   \
                     "DISTRIB_DESCRIPTION=\"Ubuntu 6.06.1 LTS\"\n"


def get_fqdn():
    return "ooga.local"


class ComputerInfoTest(LandscapeTest):

    helpers = [MonitorHelper]

    sample_memory_info = """
MemTotal:      1547072 kB
MemFree:        106616 kB
Buffers:        267088 kB
Cached:         798388 kB
SwapCached:          0 kB
Active:         728952 kB
Inactive:       536512 kB
HighTotal:      646016 kB
HighFree:        42204 kB
LowTotal:       901056 kB
LowFree:         64412 kB
SwapTotal:     1622524 kB
SwapFree:      1622524 kB
Dirty:              24 kB
Writeback:           0 kB
Mapped:         268756 kB
Slab:           105492 kB
CommitLimit:   2396060 kB
Committed_AS:  1166936 kB
PageTables:       2748 kB
VmallocTotal:   114680 kB
VmallocUsed:      6912 kB
VmallocChunk:   107432 kB
"""

    def setUp(self):
        LandscapeTest.setUp(self)
        self.lsb_release_filename = self.makeFile(SAMPLE_LSB_RELEASE)
        self.query_results = {}

        def fetch_stub(url):
            value = self.query_results[url]
            if isinstance(value, Exception):
                return fail(value)
            else:
                return succeed(value)

        self.fetch_func = fetch_stub

    def mock_config_cloud(self, plugin, result):
        """Fake out plugin.monitor.config.get("cloud")."""
        plugin.client = self.mocker.mock()
        plugin.client.config.get("cloud", None)
        self.mocker.result(result)
        self.mocker.replay()

    def test_get_fqdn(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo(get_fqdn=get_fqdn)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "computer-info")
        self.assertEqual(messages[0]["hostname"], "ooga.local")

    def test_get_real_hostname(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["type"], "computer-info")
        self.assertNotEquals(len(messages[0]["hostname"]), 0)
        self.assertTrue(re.search("\w", messages[0]["hostname"]))

    def test_only_report_changed_hostnames(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo(get_fqdn=get_fqdn)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

    def test_report_changed_hostnames(self):

        def hostname_factory(hostnames=["ooga", "wubble", "wubble"]):
            i = 0
            while i < len(hostnames):
                yield hostnames[i]
                i = i + 1

        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo(get_fqdn=hostname_factory().next)
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["hostname"], "ooga")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["hostname"], "wubble")

    def test_get_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        meminfo_filename = self.makeFile(self.sample_memory_info)
        plugin = ComputerInfo(meminfo_file=meminfo_filename)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        message = messages[0]
        self.assertEqual(message["type"], "computer-info")
        self.assertEqual(message["total-memory"], 1510)
        self.assertEqual(message["total-swap"], 1584)

    def test_get_real_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        self.makeFile(self.sample_memory_info)
        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "computer-info")
        self.assertTrue(isinstance(message["total-memory"], int))
        self.assertTrue(isinstance(message["total-swap"], int))

    def test_wb_report_changed_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin._get_memory_info = lambda: (1510, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["total-memory"], 1510)
        self.assertTrue("total-swap" in message)

        plugin._get_memory_info = lambda: (2048, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEqual(message["total-memory"], 2048)
        self.assertTrue("total-swap" not in message)

    def test_wb_report_changed_total_swap(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin._get_memory_info = lambda: (1510, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["total-swap"], 1584)
        self.assertTrue("total-memory" in message)

        plugin._get_memory_info = lambda: (1510, 2048)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEqual(message["total-swap"], 2048)
        self.assertTrue("total-memory" not in message)

    def test_get_distribution(self):
        """
        Various details about the distribution should be reported by
        the plugin.  This test ensures that the right kinds of details
        end up in messages produced by the plugin.
        """
        self.mstore.set_accepted_types(["distribution-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "distribution-info")
        self.assertTrue("distributor-id" in message)
        self.assertTrue("description" in message)
        self.assertTrue("release" in message)
        self.assertTrue("code-name" in message)

    def test_get_sample_distribution(self):
        """
        Sample data is used to ensure that expected values end up in
        the distribution data reported by the plugin.
        """
        self.mstore.set_accepted_types(["distribution-info"])
        plugin = ComputerInfo(lsb_release_filename=self.lsb_release_filename)
        self.monitor.add(plugin)

        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "distribution-info")
        self.assertEqual(message["distributor-id"], "Ubuntu")
        self.assertEqual(message["description"], "Ubuntu 6.06.1 LTS")
        self.assertEqual(message["release"], "6.06")
        self.assertEqual(message["code-name"], "dapper")

    def test_report_once(self):
        """
        Distribution data shouldn't be reported unless it's changed
        since the last time it was reported.
        """
        self.mstore.set_accepted_types(["distribution-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0]["type"], "distribution-info")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(len(messages), 1)

    def test_wb_report_changed_distribution(self):
        """
        When distribution data changes, the new data should be sent to
        the server.
        """
        self.mstore.set_accepted_types(["distribution-info"])
        plugin = ComputerInfo(lsb_release_filename=self.lsb_release_filename)
        self.monitor.add(plugin)

        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "distribution-info")
        self.assertEqual(message["distributor-id"], "Ubuntu")
        self.assertEqual(message["description"], "Ubuntu 6.06.1 LTS")
        self.assertEqual(message["release"], "6.06")
        self.assertEqual(message["code-name"], "dapper")

        plugin._lsb_release_filename = self.makeFile("""\
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=6.10
DISTRIB_CODENAME=edgy
DISTRIB_DESCRIPTION="Ubuntu 6.10"
""")
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEqual(message["type"], "distribution-info")
        self.assertEqual(message["distributor-id"], "Ubuntu")
        self.assertEqual(message["description"], "Ubuntu 6.10")
        self.assertEqual(message["release"], "6.10")
        self.assertEqual(message["code-name"], "edgy")

    def test_unknown_distribution_key(self):
        self.mstore.set_accepted_types(["distribution-info"])
        lsb_release_filename = self.makeFile("""\
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=6.10
DISTRIB_CODENAME=edgy
DISTRIB_DESCRIPTION="Ubuntu 6.10"
DISTRIB_NEW_UNEXPECTED_KEY=ooga
""")
        plugin = ComputerInfo(lsb_release_filename=lsb_release_filename)
        self.monitor.add(plugin)

        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEqual(message["type"], "distribution-info")
        self.assertEqual(message["distributor-id"], "Ubuntu")
        self.assertEqual(message["description"], "Ubuntu 6.10")
        self.assertEqual(message["release"], "6.10")
        self.assertEqual(message["code-name"], "edgy")

    def test_resynchronize(self):
        """
        If a reactor event "resynchronize" is received, messages for
        all computer info should be generated.
        """
        self.mstore.set_accepted_types(["distribution-info", "computer-info"])
        meminfo_filename = self.makeFile(self.sample_memory_info)
        plugin = ComputerInfo(get_fqdn=get_fqdn,
                              meminfo_file=meminfo_filename,
                              lsb_release_filename=self.lsb_release_filename,
                              root_path=self.makeDir())
        self.monitor.add(plugin)
        plugin.exchange()
        self.reactor.fire("resynchronize", scopes=["computer"])
        plugin.exchange()
        computer_info = {"type": "computer-info", "hostname": "ooga.local",
                         "timestamp": 0, "total-memory": 1510,
                         "total-swap": 1584}
        dist_info = {"type": "distribution-info",
                     "code-name": "dapper", "description": "Ubuntu 6.06.1 LTS",
                     "distributor-id": "Ubuntu", "release": "6.06"}
        self.assertMessages(self.mstore.get_pending_messages(),
                            [computer_info, dist_info,
                             computer_info, dist_info])

    def test_computer_info_call_on_accepted(self):
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, ANY, urgent=True)
        self.mocker.replay()

        self.mstore.set_accepted_types(["computer-info"])
        self.reactor.fire(("message-type-acceptance-changed", "computer-info"),
                          True)

    def test_distribution_info_call_on_accepted(self):
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, ANY, urgent=True)
        self.mocker.replay()

        self.mstore.set_accepted_types(["distribution-info"])
        self.reactor.fire(("message-type-acceptance-changed",
                           "distribution-info"),
                          True)

    def test_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        plugin = ComputerInfo()
        self.monitor.add(plugin)
        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["distribution-info", "computer-info"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])

    def test_meta_data(self):
        """
        L{ComputerInfo} sends extra meta data the meta-data.d directory
        if it's present.

        Each file name is used as a key in the meta-data dict and the file's
        contents are used as values.

        This allows, for example, the landscape-client charm to send
        information about the juju environment to the landscape server.
        """
        meta_data_dir = self.monitor.config.meta_data_path
        os.mkdir(meta_data_dir)
        create_file(os.path.join(meta_data_dir, "juju-env-uuid"), "uuid1")
        create_file(os.path.join(meta_data_dir, "juju-unit-name"), "unit/0")
        self.mstore.set_accepted_types(["computer-info"])

        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(1, len(messages))
        meta_data = messages[0]["meta-data"]
        self.assertEqual(2, len(meta_data))
        self.assertEqual("uuid1", meta_data["juju-env-uuid"])
        self.assertEqual("unit/0", meta_data["juju-unit-name"])

    def test_meta_data_no_directory(self):
        """
        L{ComputerInfo} doesn't include the meta-data key if there is no
        meta-data.d directory.
        """
        meta_data_dir = self.monitor.config.meta_data_path
        self.assertFalse(os.path.exists(meta_data_dir))
        self.mstore.set_accepted_types(["computer-info"])

        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(1, len(messages))
        self.assertNotIn("meta-data", messages[0])

    def test_meta_data_empty_directory(self):
        """
        L{ComputerInfo} doesn't include the meta-data key if the
        meta-data.d directory doesn't contain any files.
        """
        meta_data_dir = self.monitor.config.meta_data_path
        os.mkdir(meta_data_dir)
        self.mstore.set_accepted_types(["computer-info"])

        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEqual(1, len(messages))
        self.assertNotIn("meta-data", messages[0])

    def test_cloud_meta_data(self):
        """
        L{ComputerInfo} includes the cloud-meta-data key when the cloud
        information is available.
        """
        self.mstore.set_accepted_types(["computer-info"])
        
	plugin = ComputerInfo()
        plugin._cloud_meta_data = {"instance_key": "i00001"}
 	self.monitor.add(plugin)
	plugin.exchange()
	messages = self.mstore.get_pending_messages()
	self.assertEqual(1, len(messages))
        self.assertIn("meta-data", messages[0])
        self.assertEqual("i00001", messages[0]["meta-data"]["instance_key"])

    def add_query_result(self, name, value):
        """
        Add a url to self.query_results that is then available through
        self.fetch_func.
        """
        url = "http://169.254.169.254/latest/meta-data/" + name
        self.query_results[url] = value
        print "query results", self.query_results

    def test_fetch_cloud_meta_data(self):
        """
        L{_fetch_cloud_meta_data} retrieves instance information from the
        EC2 api and temporarily stores it.
        """
        self.add_query_result("instance-id", "i00001")
        self.add_query_result("ami-id", "ami-00002")
        self.add_query_result("instance-type", "hs1.8xlarge")

        plugin = ComputerInfo(fetch_async=self.fetch_func)
        self.mock_config_cloud(plugin, True)

        plugin._fetch_cloud_meta_data()
        self.assertEqual({"instance_key": u"i00001", "image_key": u"ami-00002",
                          "instance_type": u"hs1.8xlarge"},
                         plugin._cloud_meta_data)

    def test_fetch_cloud_meta_data_cloud_false(self):
        """
        L{_fetch_cloud_meta_data} does not fetch cloud meta data when the
        cloud config setting is false.
        """
        plugin = ComputerInfo(fetch_async=self.fetch_func)
        self.mock_config_cloud(plugin, False)

        plugin._fetch_cloud_meta_data()
        self.assertEqual({}, plugin._cloud_meta_data)

    def test_fetch_cloud_meta_data_cloud_not_set(self):
        """
        L{_fetch_cloud_meta_data} does not fetch cloud meta data when the
        cloud config setting is unset.
        """
        plugin = ComputerInfo(fetch_async=self.fetch_func)
        self.mock_config_cloud(plugin, None)

        plugin._fetch_cloud_meta_data()

        self.assertEqual({}, plugin._cloud_meta_data)

    def test_fetch_cloud_meta_data_bad_result(self):
        """
        L{_fetch_cloud_meta_data} leaves _cloud_meta_data unmodified when
        faced with errors from the EC2 api.
        """
        self.log_helper.ignore_errors(HTTPCodeError)
        self.add_query_result("instance-id", "i7337")
        self.add_query_result("ami-id", HTTPCodeError(404, "notfound"))
        self.add_query_result("instance-type", "hs1.8xlarge")
        plugin = ComputerInfo(fetch_async=self.fetch_func)
        self.mock_config_cloud(plugin, True)

        plugin._fetch_cloud_meta_data()

        self.assertEqual({}, plugin._cloud_meta_data)

    def test_fetch_cloud_meta_data_utf8(self):
        """
        L{_fetch_cloud_meta_data} decodes utf-8 strings returned from the
        external service.
        """
        self.add_query_result("instance-id", "i00001")
        self.add_query_result("ami-id", "asdf\xe1\x88\xb4")
        self.add_query_result("instance-type", "m1.large")
        plugin = ComputerInfo(fetch_async=self.fetch_func)
        self.mock_config_cloud(plugin, True)

        plugin._fetch_cloud_meta_data()

        self.assertEqual({"instance_key": u"i00001", "image_key": u"asdf\u1234",
                          "instance_type": u"m1.large"},
                         plugin._cloud_meta_data)

