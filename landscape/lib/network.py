"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import array
import fcntl
import platform
import socket
import struct


# from header /usr/include/bits/ioctls.h
SIOCGIFCONF = 0x8912
SIOCGIFNETMASK = 0x891b
SIOCGIFBRDADDR = 0x8919
SIOCGIFADDR = 0x8915
SIOCGIFHWADDR = 0x8927


# struct definition from header /usr/include/net/if.h
# the struct size varies according to the platform arch size
# a minimal c program was used to determine the size of the
# struct, standard headers removed for brevity.
"""
#include <linux/if.h>
int main() {
  printf("Size of struct %lu\n", sizeof(struct ifreq));
}
"""

IF_STRUCT_SIZE_32 = 32
IF_STRUCT_SIZE_64 = 40


def is_64():
    """
    Determine if the platform is a 64 bit platform. Assumption
    is that it is 32 bits otherwise.
    """
    return platform.architecture('/bin/bash')[0] == '64Bit'


# initialize the struct size as per the machine's archictecture
IF_STRUCT_SIZE = is_64() and IF_STRUCT_SIZE_64 or IF_STRUCT_SIZE_32


def get_active_interfaces():
    """
    Returns a sequence of all active network interface names.
    """
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_IP)
    max_interfaces = 128

    # setup an an array to hold our response, and initialized to null strings.
    interfaces = array.array('B', '\0' * max_interfaces * IF_STRUCT_SIZE)
    buffer_size = interfaces.buffer_info()[0]
    packed_bytes = struct.pack(
        'iL', max_interfaces * IF_STRUCT_SIZE, buffer_size)

    byte_length = struct.unpack(
        'iL', fcntl.ioctl(sock.fileno(), SIOCGIFCONF, packed_bytes))[0]

    result = interfaces.tostring()

    # generator over the interface names
    for index in range(0, byte_length, IF_STRUCT_SIZE):
        ifreq_struct = result[index:index+IF_STRUCT_SIZE]
        interface_name = ifreq_struct[:ifreq_struct.index('\0')]
        yield interface_name


def get_broadcast_address(interface):
    """
    Return the broadcast address associated to an interface.

    @param interface: The name of the interface.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        sock.fileno(),
        SIOCGIFBRDADDR,
        struct.pack('256s', interface[:15]))[20:24])


def get_netmask(interface):
    """
    Return the network mask associated to an interface.

    @param interface: The name of the interface.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        sock.fileno(),
        SIOCGIFNETMASK,
        struct.pack('256s', interface[:15]))[20:24])


def get_ip_address(interface):
    """
    Return the ip address associated to the interface.

    @param interface: The name of the interface.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        sock.fileno(),
        SIOCGIFBRDADDR,
        struct.pack('256s', interface[:15]))[20:24])


def get_mac_address(interface):
    """
    Return the hardware mac address for an interface in human friendly form,
    ie. six colon separated groups of two hexadecimal digits.

    @param interface: The name of the interface.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mac_address = fcntl.ioctl(
        sock.fileno(), SIOCGIFHWADDR, struct.pack('256s', interface[:15]))
    return ''.join(['%02x:' % ord(char) for char in mac_address[18:24]])[:-1]


def get_active_device_info():
    """
    Returns a dictionary containing information on each active network
    interface present on a machine.
    """
    results = []

    for interface in get_active_interfaces():
        interface_info = {"interface": interface}
        interface_info['ip_address'] = get_ip_address(interface)
        interface_info['mac_address'] = get_mac_address(interface)
        interface_info['broadcast_address'] = get_broadcast_address(interface)
        interface_info['netmask'] = get_netmask(interface)
        results.append(interface_info)
    return results


def get_network_traffic(source_file="/proc/net/dev"):
    """
    Retrieves an array of information regarding the network activity per
    network interface.
    """
    netdev = open(source_file, "r")
    lines = netdev.readlines()
    netdev.close()

    # parse out the column headers as keys
    _, receive_columns, transmit_columns = lines[1].split("|")
    columns = ["recv_%s" % column for column in receive_columns.split()]
    columns.extend(["send_%s" % column for column in transmit_columns.split()])

    # parse out the network devices
    devices = {}
    for line in lines[2:]:
        if not ":" in line:
            continue
        device, data = line.split(":")
        device = device.strip()
        devices[device] = dict(zip(columns, map(long, data.split())))

    return devices

if __name__ == '__main__':
    import pprint
    pprint.pprint(get_active_device_info())
