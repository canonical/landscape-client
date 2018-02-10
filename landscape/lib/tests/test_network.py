import array
import socket
import unittest

from mock import patch, ANY, mock_open
from subprocess import Popen, PIPE

from landscape.lib import testing
from landscape.lib.network import (
    get_network_traffic, get_active_device_info, get_active_interfaces,
    get_fqdn, get_network_interface_speed)


class BaseTestCase(testing.HelperTestCase, unittest.TestCase):
    pass


class NetworkInfoTest(BaseTestCase):

    @patch("landscape.lib.network.get_network_interface_speed")
    def test_get_active_device_info(self, mock_get_network_interface_speed):
        """
        Device info returns a sequence of information about active
        network devices, compare and verify the output against
        that returned by ifconfig.
        """
        mock_get_network_interface_speed.return_value = (100, True)

        device_info = get_active_device_info()
        process = Popen(
            ["/sbin/ifconfig"], stdout=PIPE, env={"LC_ALL": "C"})
        result = process.communicate()[0].decode("ascii")
        interface_blocks = dict(
            [(block.split()[0].strip(":"), block.upper()) for block in
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
            self.assertEqual(100, device["speed"])
            self.assertEqual(True, device["duplex"])

        self.assertTrue(mock_get_network_interface_speed.call_count >= 1)
        mock_get_network_interface_speed.assert_called_with(ANY, ANY)

    def test_skip_loopback(self):
        """The C{lo} interface is not reported by L{get_active_device_info}."""
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("lo", interfaces)

    @patch("landscape.lib.network.get_active_interfaces")
    def test_skip_vlan(self, mock_get_active_interfaces):
        """VLAN interfaces are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces.side_effect = lambda sock: (
            list(get_active_interfaces(sock)) + [b"eth0.1"])
        device_info = get_active_device_info()
        mock_get_active_interfaces.assert_called_with(ANY)
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("eth0.1", interfaces)

    @patch("landscape.lib.network.get_active_interfaces")
    def test_skip_alias(self, mock_get_active_interfaces):
        """Interface aliases are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces.side_effect = lambda sock: (
            list(get_active_interfaces(sock)) + [b"eth0:foo"])
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("eth0:foo", interfaces)

    @patch("struct.unpack")
    @patch("fcntl.ioctl")
    def test_duplicate_network_interfaces(self, mock_ioctl, mock_unpack):
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
            b"lo\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02"
            b"\x00\x00\x00\x7f\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00eth1:pub\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x02\x00\x00\x00\xc8\xb4\xc4.\x00\x00\x00\x00\x00\x00\x00"
            b"\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00br1:metadata\x00\x00\x00\x00\x02"
            b"\x00\x00\x00\xa9\xfe\xa9\xfe\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00br1:0\x00\x00\x00\x00\x00\x00\x00"
            b"\x00"
            b"\x00\x00\x00\x02\x00\x00\x00\xc9\x19\x1f\x1d\x00\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00br1\x00\x00\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\xc0\xa8d"
            b"\x1d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00br1:priv\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00\x00\xac"
            b"\x13\x02\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\x00br1:priv\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x00"
            b"\x00\xac\x13\x02A")

        fake_array = array.array("B", response + b"\0" * 4855)

        with patch("array.array") as mock_array:
            mock_array.return_value = fake_array
            mock_ioctl.return_value = 0
            mock_unpack.return_value = (280, 38643456)

            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
            interfaces = list(get_active_interfaces(sock))

        mock_array.assert_called_with("B", ANY)
        mock_ioctl.assert_called_with(ANY, ANY, ANY)
        mock_unpack.assert_called_with("iL", ANY)

        self.assertEqual(
            [b"lo", b"eth1:pub", b"br1:metadata",
             b"br1:0", b"br1", b"br1:priv"],
            interfaces)

    def test_get_network_traffic(self):
        """
        Network traffic is assessed via reading /proc/net/dev, verify
        the parsed output against a known sample.
        """
        m = mock_open(read_data=test_proc_net_dev_output)
        with patch('landscape.lib.network.open', m):
            traffic = get_network_traffic()
        m.assert_called_with("/proc/net/dev", "r")
        self.assertEqual(traffic, test_proc_net_dev_parsed)


# exact output of cat /proc/net/dev snapshot with line continuations for pep8
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


class FQDNTest(BaseTestCase):

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


class NetworkInterfaceSpeedTest(BaseTestCase):

    @patch("struct.unpack")
    @patch("fcntl.ioctl")
    def test_get_network_interface_speed(self, mock_ioctl, mock_unpack):
        """
        The link speed is reported as unpacked from the ioctl() call.
        """
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        # ioctl always succeeds
        mock_unpack.return_value = (100, False)

        result = get_network_interface_speed(sock, b"eth0")

        mock_ioctl.assert_called_with(ANY, ANY, ANY)
        mock_unpack.assert_called_with("12xHB28x", ANY)

        self.assertEqual((100, False), result)

    @patch("struct.unpack")
    @patch("fcntl.ioctl")
    def test_unplugged(self, mock_ioctl, mock_unpack):
        """
        The link speed for an unplugged interface is reported as 0.
        """
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)

        # ioctl always succeeds
        mock_unpack.return_value = (65535, False)

        result = get_network_interface_speed(sock, b"eth0")

        mock_ioctl.assert_called_with(ANY, ANY, ANY)
        mock_unpack.assert_called_with("12xHB28x", ANY)

        self.assertEqual((0, False), result)

    @patch("fcntl.ioctl")
    def test_get_network_interface_speed_not_supported(self, mock_ioctl):
        """
        Some drivers do not report the needed interface speed. In this case
        an C{IOError} with errno 95 is raised ("Operation not supported").
        If such an error is rasied, report the speed as -1.
        """
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        theerror = IOError()
        theerror.errno = 95
        theerror.message = "Operation not supported"

        # ioctl always raises
        mock_ioctl.side_effect = theerror

        result = get_network_interface_speed(sock, b"eth0")

        mock_ioctl.assert_called_with(ANY, ANY, ANY)

        self.assertEqual((-1, False), result)

    @patch("fcntl.ioctl")
    def test_get_network_interface_speed_not_permitted(self, mock_ioctl):
        """
        In some cases (lucid seems to be affected), the ioctl() call is not
        allowed for non-root users. In that case we intercept the error and
        not report the network speed.
        """
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        theerror = IOError()
        theerror.errno = 1
        theerror.message = "Operation not permitted"

        # ioctl always raises
        mock_ioctl.side_effect = theerror

        result = get_network_interface_speed(sock, b"eth0")

        mock_ioctl.assert_called_with(ANY, ANY, ANY)

        self.assertEqual((-1, False), result)

    @patch("fcntl.ioctl")
    def test_get_network_interface_speed_other_io_error(self, mock_ioctl):
        """
        In case we get an IOError that is not "Operation not permitted", the
        exception should be raised.
        """
        sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
        theerror = IOError()
        theerror.errno = 999
        theerror.message = "Whatever"

        # ioctl always raises
        mock_ioctl.side_effect = theerror

        self.assertRaises(IOError, get_network_interface_speed, sock, b"eth0")
