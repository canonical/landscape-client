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


class CPUUsagePluginTest(LandscapeTest):
    helpers = [MonitorHelper]

    def test_get_ceph_usage_if_settings_file_does_not_exist(self):
        """
        If the config file passed to _get_ceph_usage does not exist, then
        we assume the machine is not a ceph monitor, and return None.
        """
        thefile = "/tmp/whatever/I/do/not/exist"
        plugin = CephUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_ceph_usage(config_file=thefile)
        self.assertIs(None, result)

    def test_get_ceph_usage_if_command_not_found(self):
        """
        When the ceph command cannot be found or accessed, the
        C{_get_ceph_usage} method returns None.
        """
        thefile = "/etc/hosts"  # This *does* exist
        plugin = CephUsage(create_time=self.reactor.time)

        def return_none():
            return None

        plugin._get_ceph_command_output = return_none

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage(config_file=thefile)
        self.assertIs(None, result)

    def test_get_ceph_usage(self):
        """
        When the ceph command call returns output, the _get_ceph_usage method
        returns the percentage of used space.
        """
        thefile = "/etc/hosts"
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_OUTPUT

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage(config_file=thefile)
        self.assertEqual(0.12029780564263323, result)

    def test_get_ceph_usage_empty_disk(self):
        """
        When the ceph command call returns output for empty disks, the
        _get_ceph_usage method returns 0.0 .
        """
        thefile = "/etc/hosts"
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_TEMPLATE % (0, 100, 100)

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage(config_file=thefile)
        self.assertEqual(0.0, result)

    def test_get_ceph_usage_full_disk(self):
        """
        When the ceph command call returns output for empty disks, the
        _get_ceph_usage method returns 1.0 .
        """
        thefile = "/etc/hosts"
        plugin = CephUsage(create_time=self.reactor.time)

        def return_output():
            return SAMPLE_TEMPLATE % (100, 0, 100)

        plugin._get_ceph_command_output = return_output

        self.monitor.add(plugin)

        result = plugin._get_ceph_usage(config_file=thefile)
        self.assertEqual(1.0, result)
