from functools import partial
from operator import itemgetter

from netifaces import AF_INET, AF_INET6
from twisted.internet.defer import succeed

from landscape.lib.network import get_active_device_info


class Network(object):
    """Show information about active network interfaces.

    @param get_device_info: Optionally, a function that returns information
        about network interfaces.  Defaults to L{get_active_device_info}.
    """

    def __init__(self, get_device_info=None):
        if get_device_info is None:
            get_device_info = partial(get_active_device_info, extended=True)
        self._get_device_info = get_device_info

    def register(self, sysinfo):
        """Register this plugin with the sysinfo system.

        @param sysinfo: The sysinfo registry.
        """
        self._sysinfo = sysinfo

    def run(self):
        """
        Gather information about network interfaces and write it to the
        sysinfo output.

        @return: A succeeded C{Deferred}.
        """
        device_info = self._get_device_info()
        for info in sorted(device_info, key=itemgetter('interface')):
            interface = info["interface"]
            ipv4_addresses = info["ip_addresses"].get(AF_INET, [])
            ipv6_addresses = info["ip_addresses"].get(AF_INET6, [])
            for addr in ipv4_addresses:
                self._sysinfo.add_header(
                    "IPv4 address for %s" % interface, addr['addr'])
            for addr in ipv6_addresses:
                self._sysinfo.add_header(
                    "IPv6 address for %s" % interface, addr['addr'])

        return succeed(None)
