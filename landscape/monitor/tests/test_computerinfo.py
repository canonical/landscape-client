import re
import os

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

    def test_get_fqdn(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo(get_fqdn=get_fqdn)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)
        self.assertEquals(messages[0]["type"], "computer-info")
        self.assertEquals(messages[0]["hostname"], "ooga.local")

    def test_get_real_hostname(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)
        self.assertEquals(messages[0]["type"], "computer-info")
        self.assertNotEquals(len(messages[0]["hostname"]), 0)
        self.assertTrue(re.search("\w", messages[0]["hostname"]))

    def test_only_report_changed_hostnames(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo(get_fqdn=get_fqdn)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)

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
        self.assertEquals(len(messages), 1)
        self.assertEquals(messages[0]["hostname"], "ooga")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 2)
        self.assertEquals(messages[1]["hostname"], "wubble")

    def test_get_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        meminfo_filename = self.makeFile(self.sample_memory_info)
        plugin = ComputerInfo(meminfo_file=meminfo_filename)
        self.monitor.add(plugin)
        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        message = messages[0]
        self.assertEquals(message["type"], "computer-info")
        self.assertEquals(message["total-memory"], 1510)
        self.assertEquals(message["total-swap"], 1584)

    def test_get_real_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        self.makeFile(self.sample_memory_info)
        plugin = ComputerInfo()
        self.monitor.add(plugin)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["type"], "computer-info")
        self.assertTrue(isinstance(message["total-memory"], int))
        self.assertTrue(isinstance(message["total-swap"], int))

    def test_wb_report_changed_total_memory(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin._get_memory_info = lambda: (1510, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["total-memory"], 1510)
        self.assertTrue("total-swap" in message)

        plugin._get_memory_info = lambda: (2048, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEquals(message["total-memory"], 2048)
        self.assertTrue("total-swap" not in message)

    def test_wb_report_changed_total_swap(self):
        self.mstore.set_accepted_types(["computer-info"])
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        plugin._get_memory_info = lambda: (1510, 1584)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[0]
        self.assertEquals(message["total-swap"], 1584)
        self.assertTrue("total-memory" in message)

        plugin._get_memory_info = lambda: (1510, 2048)
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEquals(message["total-swap"], 2048)
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
        self.assertEquals(message["type"], "distribution-info")
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
        self.assertEquals(message["type"], "distribution-info")
        self.assertEquals(message["distributor-id"], "Ubuntu")
        self.assertEquals(message["description"], "Ubuntu 6.06.1 LTS")
        self.assertEquals(message["release"], "6.06")
        self.assertEquals(message["code-name"], "dapper")

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
        self.assertEquals(len(messages), 1)
        self.assertTrue(messages[0]["type"], "distribution-info")

        plugin.exchange()
        messages = self.mstore.get_pending_messages()
        self.assertEquals(len(messages), 1)

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
        self.assertEquals(message["type"], "distribution-info")
        self.assertEquals(message["distributor-id"], "Ubuntu")
        self.assertEquals(message["description"], "Ubuntu 6.06.1 LTS")
        self.assertEquals(message["release"], "6.06")
        self.assertEquals(message["code-name"], "dapper")

        plugin._lsb_release_filename = self.makeFile("""\
DISTRIB_ID=Ubuntu
DISTRIB_RELEASE=6.10
DISTRIB_CODENAME=edgy
DISTRIB_DESCRIPTION="Ubuntu 6.10"
""")
        plugin.exchange()
        message = self.mstore.get_pending_messages()[1]
        self.assertEquals(message["type"], "distribution-info")
        self.assertEquals(message["distributor-id"], "Ubuntu")
        self.assertEquals(message["description"], "Ubuntu 6.10")
        self.assertEquals(message["release"], "6.10")
        self.assertEquals(message["code-name"], "edgy")

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
        self.assertEquals(message["type"], "distribution-info")
        self.assertEquals(message["distributor-id"], "Ubuntu")
        self.assertEquals(message["description"], "Ubuntu 6.10")
        self.assertEquals(message["release"], "6.10")
        self.assertEquals(message["code-name"], "edgy")

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
        self.reactor.fire("resynchronize")
        plugin.exchange()
        computer_info = {"type": "computer-info", "hostname": "ooga.local",
                         "timestamp": 0, "total-memory": 1510,
                         "total-swap": 1584, "vm-info": ""}
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
        remote_broker_mock.send_message(ANY, urgent=True)
        self.mocker.replay()

        self.mstore.set_accepted_types(["computer-info"])
        self.reactor.fire(("message-type-acceptance-changed", "computer-info"),
                          True)

    def test_distribution_info_call_on_accepted(self):
        plugin = ComputerInfo()
        self.monitor.add(plugin)

        remote_broker_mock = self.mocker.replace(self.remote)
        remote_broker_mock.send_message(ANY, urgent=True)
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
