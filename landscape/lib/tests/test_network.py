import socket
import unittest

from mock import patch, ANY, mock_open
from netifaces import (
    AF_INET,
    AF_INET6,
    AF_LINK,
    AF_UNIX,
    ifaddresses as _ifaddresses,
    interfaces as _interfaces,
)
from subprocess import Popen, PIPE

from landscape.lib import testing
from landscape.lib.network import (
    get_network_traffic, get_active_device_info, get_active_interfaces,
    get_fqdn, get_network_interface_speed, is_up)


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

        device_info = get_active_device_info(extended=False)
        process = Popen(["/sbin/ifconfig"], stdout=PIPE, env={"LC_ALL": "C"})
        result = process.communicate()[0].decode("ascii")
        interface_blocks = dict(
            [(block.split()[0].strip(":"), block.upper()) for block in
             filter(None, result.split("\n\n"))])

        for device in device_info:
            if device["mac_address"] == "00:00:00:00:00:00":
                continue
            self.assertIn(device["interface"], result)
            block = interface_blocks[device["interface"]]
            self.assertIn(device["netmask"], block)
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

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_extended_info(self, mock_interfaces, mock_ifaddresses,
                           mock_get_flags, mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 4163
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {
            AF_LINK: [
                {"addr": "aa:bb:cc:dd:ee:f0"},
                {"addr": "aa:bb:cc:dd:ee:f1"}],
            AF_INET: [
                {"addr": "192.168.0.50", "netmask": "255.255.255.0"},
                {"addr": "192.168.1.50", "netmask": "255.255.255.0"}],
            AF_INET6: [
                {"addr": "2001::1"},
                {"addr": "2002::2"}]}

        device_info = get_active_device_info(extended=True)

        self.assertEqual(
            device_info,
            [{
                'interface': 'test_iface',
                'ip_address': '192.168.0.50',
                'mac_address': 'aa:bb:cc:dd:ee:f0',
                'broadcast_address': '0.0.0.0',
                'netmask': '255.255.255.0',
                'ip_addresses': {
                    AF_INET: [
                        {'addr': '192.168.0.50', 'netmask': '255.255.255.0'},
                        {'addr': '192.168.1.50', 'netmask': '255.255.255.0'}],
                    AF_INET6: [
                        {"addr": "2001::1"},
                        {"addr": "2002::2"}]},
                'flags': 4163,
                'speed': 100,
                'duplex': True}])

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_skip_ipv6_only_in_non_extended_mode(
            self, mock_interfaces, mock_ifaddresses, mock_get_flags,
            mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 4163
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {
            AF_LINK: [{"addr": "aa:bb:cc:dd:ee:f0"}],
            AF_INET6: [{"addr": "2001::1"}]}

        device_info = get_active_device_info(extended=False)

        self.assertEqual(device_info, [])

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_ipv6_only_in_extended_mode(
            self, mock_interfaces, mock_ifaddresses, mock_get_flags,
            mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 4163
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {
            AF_LINK: [{"addr": "aa:bb:cc:dd:ee:f0"}],
            AF_INET6: [{"addr": "2001::1"}]}

        device_info = get_active_device_info(extended=True)

        self.assertEqual(
            device_info,
            [{
                'interface': 'test_iface',
                'flags': 4163,
                'speed': 100,
                'duplex': True,
                'ip_addresses': {AF_INET6: [{'addr': '2001::1'}]}}])

    def test_skip_loopback(self):
        """The C{lo} interface is not reported by L{get_active_device_info}."""
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("lo", interfaces)

    @patch("landscape.lib.network.get_active_interfaces")
    def test_skip_vlan(self, mock_get_active_interfaces):
        """VLAN interfaces are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces.side_effect = lambda: (
            list(get_active_interfaces()) + [("eth0.1", {})])
        device_info = get_active_device_info()
        self.assertTrue(mock_get_active_interfaces.called)
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("eth0.1", interfaces)

    @patch("landscape.lib.network.get_active_interfaces")
    def test_skip_alias(self, mock_get_active_interfaces):
        """Interface aliases are not reported by L{get_active_device_info}."""
        mock_get_active_interfaces.side_effect = lambda: (
            list(get_active_interfaces()) + [("eth0:foo", {})])
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("eth0:foo", interfaces)

    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_skip_iface_with_no_addr(self, mock_interfaces, mock_ifaddresses):
        mock_interfaces.return_value = _interfaces() + ["test_iface"]
        mock_ifaddresses.side_effect = lambda iface: (
            _ifaddresses(iface) if iface in _interfaces() else {})
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("test_iface", interfaces)

    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_skip_iface_with_no_ip(self, mock_interfaces, mock_ifaddresses):
        mock_interfaces.return_value = _interfaces() + ["test_iface"]
        mock_ifaddresses.side_effect = lambda iface: (
             _ifaddresses(iface) if iface in _interfaces() else {AF_UNIX: []})
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("test_iface", interfaces)

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_skip_iface_down(
            self, mock_interfaces, mock_ifaddresses, mock_get_flags,
            mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 0
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {
            AF_LINK: [{"addr": "aa:bb:cc:dd:ee:f0"}],
            AF_INET: [{"addr": "192.168.1.50", "netmask": "255.255.255.0"}]}
        device_info = get_active_device_info()
        interfaces = [i["interface"] for i in device_info]
        self.assertNotIn("test_iface", interfaces)

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_no_macaddr_no_netmask_no_broadcast(
            self, mock_interfaces, mock_ifaddresses, mock_get_flags,
            mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 4163
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {AF_INET: [{"addr": "192.168.0.50"}]}
        device_info = get_active_device_info(extended=False)
        self.assertEqual(
            device_info,
            [{
                'interface': 'test_iface',
                'ip_address': '192.168.0.50',
                'broadcast_address': '0.0.0.0',
                'mac_address': '',
                'netmask': '',
                'flags': 4163,
                'speed': 100,
                'duplex': True}])

    def test_get_network_traffic(self):
        """
        Network traffic is assessed via reading /proc/net/dev, verify
        the parsed output against a known sample.
        """
        m = mock_open(read_data=test_proc_net_dev_output)
        # Trusty's version of `mock.mock_open` does not support `readlines()`.
        m().readlines = test_proc_net_dev_output.splitlines
        with patch('landscape.lib.network.open', m, create=True):
            traffic = get_network_traffic()
        m.assert_called_with("/proc/net/dev", "r")
        self.assertEqual(traffic, test_proc_net_dev_parsed)

    @patch("landscape.lib.network.get_network_interface_speed")
    @patch("landscape.lib.network.get_flags")
    @patch("landscape.lib.network.netifaces.ifaddresses")
    @patch("landscape.lib.network.netifaces.interfaces")
    def test_ipv6_skip_link_local(
            self, mock_interfaces, mock_ifaddresses, mock_get_flags,
            mock_get_network_interface_speed):
        mock_get_network_interface_speed.return_value = (100, True)
        mock_get_flags.return_value = 4163
        mock_interfaces.return_value = ["test_iface"]
        mock_ifaddresses.return_value = {
            AF_LINK: [
                {"addr": "aa:bb:cc:dd:ee:f1"}],
            AF_INET6: [
                {"addr": "fe80::1"},
                {"addr": "2001::1"}]}

        device_info = get_active_device_info(extended=True)

        self.assertEqual(
            device_info,
            [{
                'interface': 'test_iface',
                'flags': 4163,
                'speed': 100,
                'duplex': True,
                'ip_addresses': {AF_INET6: [{"addr": "2001::1"}]}}])

    def test_is_up(self):
        self.assertTrue(is_up(1))
        self.assertTrue(is_up(1 + 2 + 64 + 4096))
        self.assertTrue(is_up(0b11111111111111))
        self.assertFalse(is_up(0))
        self.assertFalse(is_up(2 + 64 + 4096))
        self.assertFalse(is_up(0b11111111111110))


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
