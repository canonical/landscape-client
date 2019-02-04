import unittest

from landscape.lib.testing import TwistedTestCase
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.network import AF_INET, Network


class NetworkTest(TwistedTestCase, unittest.TestCase):

    def setUp(self):
        super(NetworkTest, self).setUp()
        self.result = []
        self.network = Network(lambda: self.result)
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.network)

    def test_run_returns_succeeded_deferred(self):
        """L{Network.run} always returns a succeeded C{Deferred}."""
        self.assertIs(None, self.successResultOf(self.network.run()))

    def test_run_single_interface_ipv4_address(self):
        """
        A header is written to sysinfo output for each network device reported
        by L{get_active_device_info}.
        """
        self.result = [{
            "interface": "eth0",
            "ip_address": "IGNORED",
            "ip_addresses": {
                AF_INET: [{"addr": "192.168.0.50"}]}}]

        self.network.run()
        self.assertEqual([("IPv4 address for eth0", "192.168.0.50")],
                         self.sysinfo.get_headers())

    def test_run_multiple_interface_multiple_addresses(self):
        """
        A header is written to sysinfo output for each network device reported
        by L{get_active_device_info}.
        """
        self.result = [{
            "interface": "eth0",
            "ip_address": "IGNORED",
            "ip_addresses": {
                AF_INET: [
                    {"addr": "192.168.0.50"},
                    {"addr": "192.168.1.50"}]}}, {
            "interface": "eth1",
            "ip_address": "IGNORED",
            "ip_addresses": {
                AF_INET: [
                    {"addr": "192.168.2.50"},
                    {"addr": "192.168.3.50"}]}}]

        self.network.run()
        self.assertEqual([
            ("IPv4 address for eth0", "192.168.0.50"),
            ("IPv4 address for eth0", "192.168.1.50"),
            ("IPv4 address for eth1", "192.168.2.50"),
            ("IPv4 address for eth1", "192.168.3.50")],
            self.sysinfo.get_headers())

    def test_run_without_network_devices(self):
        """
        If no network device information is available, no headers are added to
        the sysinfo output.
        """
        self.network.run()
        self.assertEqual([], self.sysinfo.get_headers())
