
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
        pass

    def test_get_mac_address(self):
        pass

    def get_ip_address(self):
        pass
