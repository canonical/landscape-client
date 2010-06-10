from twisted.internet.defer import succeed

from landscape.lib.network import get_active_device_info


class Network(object):
    """Show information about active network interfaces.

    @param get_device_info: Optionally, a function that returns information
        about network interfaces.  Defaults to L{get_active_device_info}.
    """

    def __init__(self, get_device_info=None):
        if get_device_info is None:
            get_device_info = get_active_device_info
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
        for info in self._get_device_info():
            interface = info["interface"]
            ip_address = info["ip_address"]
            self._sysinfo.add_header("IP address for %s" % interface,
                                     ip_address)
        return succeed(None)
