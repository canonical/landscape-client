import array
from cStringIO import StringIO
import socket
from subprocess import Popen, PIPE
from landscape.tests.helpers import LandscapeTest

from landscape.lib.network import (
    get_network_traffic, get_active_device_info, get_active_interfaces,
    get_fqdn)
from landscape.tests.mocker import ANY


class NetworkInfoTest(LandscapeTest):

    def test_get_active_device_info(self):
        """
        Device info returns a sequence of information about active
        network devices, compare and verify the output against
        that returned by ifconfig.
        """
        device_info = get_active_device_info()
        result = Popen(["/sbin/ifconfig"], stdout=PIPE).communicate()[0]
        interface_blocks = dict(
            [(block.split()[0], block.upper()) for block in
             filter(None, result.split("\n\n"))])

        for device in device_info:
            if device["mac_address"] == "00:00:00:00:00:00":
                continue
            self.assertTrue(device["interface"] in result)
            block = interface_blocks[device["interface"]]
            self.assertTrue(device["netmask"] in block)
            self.assertIn(device["ip_address"], block)
            self.assertIn(device["mac_address"].upper(), block)
            self.assertIn(device["broadcast_address"], block)
            flags = device["flags"]
            if flags & 1:
                self.assertIn("UP", block)
            if flags & 2:
                self.assertIn("BROADCAST", block)
            if flags & 64:
                self.assertIn("RUNNING", block)
            if flags & 4096:
                self.assertIn("MULTICAST", block)

    def test_skip_loopback(self):
        """The C{lo} interface is not reported by L{get_active_device_info}."""
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("lo", interfaces)

    def test_skip_vlan(self):
        """VLAN interfaces are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces = self.mocker.replace(get_active_interfaces)
        mock_get_active_interfaces(ANY)
        self.mocker.result(["eth0", "eth0.1", "eth0.2"])
        self.mocker.replay()
        device_info = get_active_device_info()
        self.assertEqual(["eth0"], [i["interface"] for i in device_info])

    def test_skip_alias(self):
        """Interface aliases are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces = self.mocker.replace(get_active_interfaces)
        mock_get_active_interfaces(ANY)
        self.mocker.result(["eth0", "eth0:foo", "eth0:bar"])
        self.mocker.replay()
        device_info = get_active_device_info()
        self.assertEqual(["eth0"], [i["interface"] for i in device_info])

    def test_duplicate_network_interfaces(self):
        """
        L{get_active_interfaces} doesn't return duplicate network interfaces.
        The call to C{fcntl.ioctl} might return the same interface several
        times, so we make sure to clean it up.
        """
        import landscape.lib.network
        original_struct_size = landscape.lib.network.IF_STRUCT_SIZE
        landscape.lib.network.IF_STRUCT_SIZE = 40
        self.addCleanup(
            setattr, landscape.lib.network, "IF_STRUCT_SIZE",
            original_struct_size)
        # This is a fake response observed to return the same interface several
        # times (here, br1:priv)
        response = (
            "lo\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02"
            "\x00\x00\x00\x7f\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x00\x00\x00\x00\x00\x00eth1:pub\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x02\x00\x00\x00\xc8\xb4\xc4.\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x00\x00\x00\x00\x00\x00\x00br1:metadata\x00\x00\x00\x00\x02"
            "\x00\x00\x00\xa9\xfe\xa9\xfe\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x00\x00\x00\x00\x00\x00br1:0\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x00\x00\x02\x00\x00\x00\xc9\x19\x1f\x1d\x00\x00\x00\x00\x00"
            "\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00br1\x00\x00\x00\x00"
            "\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\xc0\xa8d"
            "\x1d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00br1:priv\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\xac"
            "\x13\x02\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            "\x00\x00\x00br1:priv\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00"
            "\x00\xac\x13\x02A")

        fake_array = array.array("B", response + "\0" * 4855)
        mock_array = self.mocker.replace("array")
        mock_array.array("B", ANY)
        self.mocker.result(fake_array)

        mock_ioctl = self.mocker.replace("fcntl")
        mock_ioctl.ioctl(ANY, ANY, ANY)
        self.mocker.result(0)

        mock_unpack = self.mocker.replace("struct")
        mock_unpack.unpack("iL", ANY)
        self.mocker.result((280, 38643456))

        self.mocker.replay()

        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        self.assertEqual(
            ["lo", "eth1:pub", "br1:metadata", "br1:0", "br1", "br1:priv"],
            list(get_active_interfaces(sock)))

    def test_get_network_traffic(self):
        """
        Network traffic is assessed via reading /proc/net/dev, verify
        the parsed output against a known sample.
        """
        open_mock = self.mocker.replace("__builtin__.open")
        open_mock("/proc/net/dev", "r")
        self.mocker.result(StringIO(test_proc_net_dev_output))
        self.mocker.replay()
        traffic = get_network_traffic()
        self.assertEqual(traffic, test_proc_net_dev_parsed)


#exact output of cat /proc/net/dev snapshot with line continuations for pep8
test_proc_net_dev_output = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    \
 packets errs drop fifo colls carrier compressed
    lo:3272627934 3321049    0    0    0     0          0         0 3272627934\
    3321049    0    0    0     0       0          0
  eth0: 6063748   12539    0    0    0     0          0        62  2279693\
  12579    0    0    0    19       0          0
"""

test_proc_net_dev_parsed = {
    "lo": {"recv_bytes": 3272627934,
          "recv_packets": 3321049,
          "recv_errs": 0,
          "recv_drop": 0,
          "recv_fifo": 0,
          "recv_frame": 0,
          "recv_compressed": 0,
          "recv_multicast": 0,
          "send_bytes": 3272627934,
          "send_packets": 3321049,
          "send_errs": 0,
          "send_drop": 0,
          "send_fifo": 0,
          "send_colls": 0,
          "send_carrier": 0,
          "send_compressed": 0},
    "eth0": {"recv_bytes": 6063748,
            "recv_packets": 12539,
            "recv_errs": 0,
            "recv_drop": 0,
            "recv_fifo": 0,
            "recv_frame": 0,
            "recv_compressed": 0,
            "recv_multicast": 62,
            "send_bytes": 2279693,
            "send_packets": 12579,
            "send_errs": 0,
            "send_drop": 0,
            "send_fifo": 0,
            "send_colls": 19,
            "send_carrier": 0,
            "send_compressed": 0}}


class FQDNTest(LandscapeTest):

    def test_default_fqdn(self):
        """
        C{get_fqdn} returns the output of C{socket.getfqdn} if it returns
        something sensible.
        """
        self.addCleanup(setattr, socket, "getfqdn", socket.getfqdn)
        socket.getfqdn = lambda: "foo.bar"
        self.assertEqual("foo.bar", get_fqdn())

    def test_getaddrinfo_fallback(self):
        """
        C{get_fqdn} falls back to C{socket.getaddrinfo} with the
        C{AI_CANONNAME} flag if C{socket.getfqdn} returns a local hostname.
        """
        self.addCleanup(setattr, socket, "getfqdn", socket.getfqdn)
        socket.getfqdn = lambda: "localhost6.localdomain6"
        self.assertNotIn("localhost", get_fqdn())
