from __future__ import absolute_import

"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import array
import fcntl
import socket
import struct
import errno
import logging

import netifaces
from twisted.python.compat import long, _PY3

__all__ = ["get_active_device_info", "get_network_traffic"]


SIOCGIFFLAGS = 0x8913  # from header /usr/include/bits/ioctls.h
SIOCETHTOOL = 0x8946  # As defined in include/uapi/linux/sockios.h
ETHTOOL_GSET = 0x00000001  # Get status command.


def is_64():
    """Returns C{True} if the platform is 64-bit, otherwise C{False}."""
    return struct.calcsize("l") == 8


def is_up(flags):
    """Returns C{True} if the interface is up, otherwise C{False}.

    @param flags: the integer value of an interface's flags.
    @see /usr/include/linux/if.h for the meaning of the flags.
    """
    return flags & 1


def get_active_interfaces():
    """Generator yields (active network interface name, address data) tuples.

    Address data is formatted exactly like L{netifaces.ifaddresses}, e.g.::

        ('eth0', {
            AF_LINK: [
                {'addr': '...', 'broadcast': '...'}, ],
            AF_INET: [
                {'addr': '...', 'broadcast': '...', 'netmask': '...'},
                {'addr': '...', 'broadcast': '...', 'netmask': '...'},
                ...],
            AF_INET6: [
                {'addr': '...', 'netmask': '...'},
                {'addr': '...', 'netmask': '...'},
                ...], })

    Interfaces with no IP address are ignored.
    """
    for interface in netifaces.interfaces():
        ifaddresses = netifaces.ifaddresses(interface)
        # Skip interfaces with no IPv4 or IPv6 addresses.
        inet_addr = ifaddresses.get(netifaces.AF_INET, [{}])[0].get('addr')
        inet6_addr = ifaddresses.get(netifaces.AF_INET6, [{}])[0].get('addr')
        if inet_addr or inet6_addr:
            yield interface, ifaddresses


def get_ip_addresses(ifaddresses):
    """Return all IP addresses of an interfaces.

    Returns the same structure as L{ifaddresses}, but filtered to keep
    IP addresses only.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses} or
        the address data in L{get_active_interfaces}'s output.
    """
    results = {}
    if netifaces.AF_INET in ifaddresses:
        results[netifaces.AF_INET] = ifaddresses[netifaces.AF_INET]
    if netifaces.AF_INET6 in ifaddresses:
        # Ignore link-local IPv6 addresses (fe80::/10).
        global_addrs = [addr for addr in ifaddresses[netifaces.AF_INET6]
                        if not addr['addr'].startswith('fe80:')]
        if global_addrs:
            results[netifaces.AF_INET6] = global_addrs

    return results


def get_broadcast_address(ifaddresses):
    """Return the broadcast address associated to an interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses} or
        the address data in L{get_active_interfaces}'s output.
    """
    return ifaddresses[netifaces.AF_INET][0].get('broadcast', '0.0.0.0')


def get_netmask(ifaddresses):
    """Return the network mask associated to an interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses} or
        the address data in L{get_active_interfaces}'s output.
    """
    return ifaddresses[netifaces.AF_INET][0].get('netmask', '')


def get_ip_address(ifaddresses):
    """Return the first IPv4 address associated to the interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses} or
        the address data in L{get_active_interfaces}'s output.
    """
    return ifaddresses[netifaces.AF_INET][0]['addr']


def get_mac_address(ifaddresses):
    """
    Return the hardware MAC address for an interface in human friendly form,
    ie. six colon separated groups of two hexadecimal digits, if available;
    otherwise an empty string.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses} or
        the address data in L{get_active_interfaces}'s output.
    """
    if netifaces.AF_LINK in ifaddresses:
        return ifaddresses[netifaces.AF_LINK][0].get('addr', '')
    return ''


def get_flags(sock, interface):
    """Return the integer value of the interface flags for the given interface.

    @param sock: a socket instance.
    @param interface: The name of the interface.
    @see /usr/include/linux/if.h for the meaning of the flags.
    """
    data = fcntl.ioctl(
        sock.fileno(), SIOCGIFFLAGS, struct.pack("256s", interface[:15]))
    return struct.unpack("H", data[16:18])[0]


def get_active_device_info(skipped_interfaces=("lo",),
                           skip_vlan=True, skip_alias=True, extended=False):
    """
    Returns a dictionary containing information on each active network
    interface present on a machine.
    """
    results = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                             socket.IPPROTO_IP)
        for interface, ifaddresses in get_active_interfaces():
            if interface in skipped_interfaces:
                continue
            if skip_vlan and "." in interface:
                continue
            if skip_alias and ":" in interface:
                continue
            flags = get_flags(sock, interface.encode())
            if not is_up(flags):
                continue
            interface_info = {"interface": interface}
            interface_info["flags"] = flags
            speed, duplex = get_network_interface_speed(
                sock, interface.encode())
            interface_info["speed"] = speed
            interface_info["duplex"] = duplex
            ip_addresses = get_ip_addresses(ifaddresses)
            if extended:
                interface_info["ip_addresses"] = ip_addresses
            if netifaces.AF_INET in ip_addresses:
                interface_info["ip_address"] = get_ip_address(ifaddresses)
                interface_info["mac_address"] = get_mac_address(ifaddresses)
                interface_info["broadcast_address"] = get_broadcast_address(
                    ifaddresses)
                interface_info["netmask"] = get_netmask(ifaddresses)
            # Skip interfaces with no IPv4 address in non-extended mode
            # to keep backwards compatibility with single-IPv4 addr support.
            if netifaces.AF_INET in ip_addresses or extended:
                results.append(interface_info)
    finally:
        del sock

    return results


def get_network_traffic(source_file="/proc/net/dev"):
    """
    Retrieves an array of information regarding the network activity per
    network interface.
    """
    with open(source_file, "r") as netdev:
        lines = netdev.readlines()

    # Parse out the column headers as keys.
    _, receive_columns, transmit_columns = lines[1].split("|")
    columns = ["recv_%s" % column for column in receive_columns.split()]
    columns.extend(["send_%s" % column for column in transmit_columns.split()])

    # Parse out the network devices.
    devices = {}
    for line in lines[2:]:
        if ":" not in line:
            continue
        device, data = line.split(":")
        device = device.strip()
        devices[device] = dict(zip(columns, map(long, data.split())))
    return devices


def get_fqdn():
    """
    Return the current fqdn of the machine, trying hard to return a meaningful
    name.

    In particular, it means working against a NetworkManager bug which seems to
    make C{getfqdn} return localhost6.localdomain6 for machine without a domain
    since Maverick.
    """
    fqdn = socket.getfqdn()
    if "localhost" in fqdn:
        # Try the heavy artillery
        fqdn = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET,
                                  socket.SOCK_DGRAM, socket.IPPROTO_IP,
                                  socket.AI_CANONNAME)[0][3]
        if "localhost" in fqdn:
            # Another fallback
            fqdn = socket.gethostname()
    return fqdn


def get_network_interface_speed(sock, interface_name):
    """
    Return the ethernet device's advertised link speed.

    The return value can be one of:
        * 10, 100, 1000, 2500, 10000: The interface speed in Mbps
        * -1: The interface does not support querying for max speed, such as
          virtio devices for instance.
        * 0: The cable is not connected to the interface. We cannot measure
          interface speed, but could if it was plugged in.
    """
    cmd_struct = struct.pack("I39s", ETHTOOL_GSET, b"\x00" * 39)
    status_cmd = array.array("B", cmd_struct)
    packed = struct.pack("16sP", interface_name, status_cmd.buffer_info()[0])

    speed = -1
    try:
        fcntl.ioctl(sock, SIOCETHTOOL, packed)  # Status ioctl() call
        if _PY3:
            res = status_cmd.tobytes()
        else:
            res = status_cmd.tostring()
        speed, duplex = struct.unpack("12xHB28x", res)
    except (IOError, OSError) as e:
        if e.errno == errno.EPERM:
            logging.warn("Could not determine network interface speed, "
                         "operation not permitted.")
        elif e.errno != errno.EOPNOTSUPP and e.errno != errno.EINVAL:
            raise e
        speed = -1
        duplex = False

    # Drivers apparently report speed as 65535 when the link is not available
    # (cable unplugged for example).
    if speed == 65535:
        speed = 0

    # The drivers report "duplex" to be 255 when the information is not
    # available. We'll just assume it's False in that case.
    if duplex == 255:
        duplex = False
    duplex = bool(duplex)

    return speed, duplex
