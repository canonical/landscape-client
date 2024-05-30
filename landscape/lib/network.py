"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import array
import errno
import fcntl
import logging
import socket
import struct

import netifaces

from landscape.lib.compat import _PY3
from landscape.lib.compat import long

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


def is_active(ifaddresses):
    """Checks if interface address data has an IP address

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    inet_addr = ifaddresses.get(netifaces.AF_INET, [{}])[0].get("addr")
    inet6_addr = ifaddresses.get(netifaces.AF_INET6, [{}])[0].get("addr")
    return bool(inet_addr or inet6_addr)


def get_ip_addresses(ifaddresses):
    """Return all IP addresses of an interfaces.

    Returns the same structure as L{ifaddresses}, but filtered to keep
    IP addresses only.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    results = {}
    if netifaces.AF_INET in ifaddresses:
        results[netifaces.AF_INET] = ifaddresses[netifaces.AF_INET]
    if netifaces.AF_INET6 in ifaddresses:
        # Ignore link-local IPv6 addresses (fe80::/10).
        global_addrs = [
            addr
            for addr in ifaddresses[netifaces.AF_INET6]
            if not addr["addr"].startswith("fe80:")
        ]
        if global_addrs:
            results[netifaces.AF_INET6] = global_addrs

    return results


def get_broadcast_address(ifaddresses):
    """Return the broadcast address associated to an interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    return ifaddresses[netifaces.AF_INET][0].get("broadcast", "0.0.0.0")


def get_netmask(ifaddresses):
    """Return the network mask associated to an interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    return ifaddresses[netifaces.AF_INET][0].get("netmask", "")


def get_ip_address(ifaddresses):
    """Return the first IPv4 address associated to the interface.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    return ifaddresses[netifaces.AF_INET][0]["addr"]


def get_mac_address(ifaddresses):
    """
    Return the hardware MAC address for an interface in human friendly form,
    ie. six colon separated groups of two hexadecimal digits, if available;
    otherwise an empty string.

    @param ifaddresses: a dict as returned by L{netifaces.ifaddresses}
    """
    if netifaces.AF_LINK in ifaddresses:
        return ifaddresses[netifaces.AF_LINK][0].get("addr", "")
    return ""


def get_flags(sock, interface):
    """Return the integer value of the interface flags for the given interface.

    @param sock: a socket instance.
    @param interface: The name of the interface.
    @see /usr/include/linux/if.h for the meaning of the flags.
    """
    data = fcntl.ioctl(
        sock.fileno(),
        SIOCGIFFLAGS,
        struct.pack("256s", interface[:15]),
    )
    return struct.unpack("H", data[16:18])[0]


def get_default_interfaces():
    """
    Returns a list of interfaces with default routes
    """
    default_table = netifaces.gateways()["default"]
    interfaces = [gateway[1] for gateway in default_table.values()]
    return interfaces


def get_filtered_if_info(filters=(), extended=False):
    """
    Returns a dictionary containing info on each active network
    interface that passes all `filters`.

    A filter is a callable that returns True if the interface should be
    skipped.
    """
    results = []

    try:
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_IP,
        )

        for interface in netifaces.interfaces():
            if any(f(interface) for f in filters):
                continue

            ifaddresses = netifaces.ifaddresses(interface)
            if (
                not is_active(ifaddresses)
                and netifaces.AF_LINK not in ifaddresses
            ):
                continue

            ifencoded = interface.encode()
            flags = get_flags(sock, ifencoded)
            ip_addresses = get_ip_addresses(ifaddresses)

            ifinfo = {"interface": interface}
            ifinfo["flags"] = flags
            ifinfo["speed"], ifinfo["duplex"] = get_network_interface_speed(
                sock,
                ifencoded,
            )

            if extended:
                ifinfo["ip_addresses"] = ip_addresses

            if netifaces.AF_INET in ip_addresses:
                ifinfo["ip_address"] = get_ip_address(ifaddresses)
                ifinfo["mac_address"] = get_mac_address(ifaddresses)
                ifinfo["broadcast_address"] = get_broadcast_address(
                    ifaddresses,
                )
                ifinfo["netmask"] = get_netmask(ifaddresses)
            elif netifaces.AF_LINK in ifaddresses and not extended:
                ifinfo["ip_address"] = "0.0.0.0"
                ifinfo["mac_address"] = get_mac_address(ifaddresses)
                ifinfo["broadcast_address"] = "0.0.0.0"
                ifinfo["netmask"] = "0.0.0.0"

            results.append(ifinfo)
    finally:
        sock.close()

    return results


def get_active_device_info(
    skipped_interfaces=("lo",),
    skip_vlan=True,
    skip_alias=True,
    extended=False,
    default_only=False,
):
    def filter_local(interface):
        return interface in skipped_interfaces

    def filter_vlan(interface):
        return "." in interface

    def filter_alias(interface):
        return ":" in interface

    # Get default interfaces here because it could be expensive and
    # there's no reason to do it more than once.
    default_ifs = get_default_interfaces()

    def filter_default(interface):
        return default_only and interface not in default_ifs

    # Tap interfaces can be extremely numerous, slowing us down
    # significantly.
    def filter_tap(interface):
        return interface.startswith("tap")

    return get_filtered_if_info(
        filters=(
            filter_tap,
            filter_local,
            filter_vlan,
            filter_alias,
            filter_default,
        ),
        extended=extended,
    )


def get_network_traffic(source_file="/proc/net/dev"):
    """
    Retrieves an array of information regarding the network activity per
    network interface.
    """
    with open(source_file, "r") as netdev:
        lines = netdev.readlines()

    # Parse out the column headers as keys.
    _, receive_columns, transmit_columns = lines[1].split("|")
    columns = [f"recv_{column}" for column in receive_columns.split()]
    columns.extend([f"send_{column}" for column in transmit_columns.split()])

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
        fqdn = socket.getaddrinfo(
            socket.gethostname(),
            None,
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_IP,
            socket.AI_CANONNAME,
        )[0][3]
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
            logging.warning(
                "Could not determine network interface speed, "
                "operation not permitted.",
            )
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
