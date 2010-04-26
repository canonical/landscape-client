from cStringIO import StringIO
from subprocess import Popen, PIPE
from landscape.tests.helpers import LandscapeTest

from landscape.lib.network import (
    get_network_traffic, get_active_device_info)


class NetworkInfoTest(LandscapeTest):

    def test_get_active_device_info(self):
        """
        Device info returns a sequence of information about active
        network devices, compare and verify the output against
        that returned by ifconfig.
        """
        device_info = get_active_device_info()
        result = Popen(["ifconfig"], stdout=PIPE).communicate()[0]
        interface_blocks = dict(
            [(block.split()[0], block) for block in
             filter(None, result.split('\n\n'))])

        for device in device_info:
            self.assertTrue(device["interface"] in result)
            block = interface_blocks[device["interface"]]
            self.assertTrue(device["netmask"] in block)

            if device["ip_address"] == "0.0.0.0": # skip local host
                continue
            self.failUnlessIn(device["ip_address"], block)
            self.failUnlessIn(device["mac_address"], block)
            self.failUnlessIn(device["broadcast_address"], block)

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
    "lo":{"recv_bytes": 3272627934,
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
    "eth0":{"recv_bytes": 6063748,
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
