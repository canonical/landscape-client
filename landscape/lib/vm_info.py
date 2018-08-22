"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import os

from landscape.lib.fs import read_text_file


def get_vm_info(root_path="/"):
    """
    Return a bytestring with the virtualization type if it's known, an empty
    bytestring otherwise.

    It loops through some possible configurations and return a bytestring with
    the name of the technology being used or None if there's no match
    """
    if _is_vm_openvz(root_path):
        return b"openvz"
    if _is_vm_xen(root_path):
        return b"xen"

    # Iterate through all dmi *_vendors, as clouds can (and will) customize
    # sysinfo values. (https://libvirt.org/formatdomain.html#elementsSysinfo)
    dmi_info_path = os.path.join(root_path, "sys/class/dmi/id")
    for dmi_info_file in ("sys_vendor", "chassis_vendor", "bios_vendor"):
        dmi_vendor_path = os.path.join(dmi_info_path, dmi_info_file)
        if not os.path.exists(dmi_vendor_path):
            continue
        vendor = _get_vm_by_vendor(dmi_vendor_path)
        if vendor:
            return vendor

    return _get_vm_legacy(root_path)


def get_container_info(run_path="/run"):
    """
    Return a string with the type of container the client is running in, if
    any, an empty string otherwise.
    """
    for filename in ("container_type", "systemd/container"):
        path = os.path.join(run_path, filename)
        if os.path.exists(path):
            return read_text_file(path).strip()
    return ""


def _is_vm_xen(root_path):
    """Check if the host is virtualized with Xen."""
    sys_xen_path = os.path.join(root_path, "sys/bus/xen/devices")
    # Paravirtualized and HVM instances have device links under the directory
    return os.path.isdir(sys_xen_path) and os.listdir(sys_xen_path)


def _is_vm_openvz(root_path):
    """Check if the host is virtualized with OpenVZ."""
    return os.path.exists(os.path.join(root_path, "proc/vz"))


def _get_vm_by_vendor(sys_vendor_path):
    """Return the VM type byte string (possibly empty) based on the vendor."""
    vendor = read_text_file(sys_vendor_path).lower()
    # Use lower-key string for vendors, since we do case-insentive match.
    # We need bytes here as required by the message schema.

    # 2018-01: AWS and DO are now returning custom sys_vendor names
    # instead of qemu. If this becomes a trend, it may be worth also checking
    # dmi/id/chassis_vendor which seems to unchanged (bochs).
    content_vendors_map = (
        ("amazon ec2", b"kvm"),
        ("bochs", b"kvm"),
        ("digitalocean", b"kvm"),
        ("google", b"gce"),
        ("innotek", b"virtualbox"),
        ("microsoft", b"hyperv"),
        ("nutanix", b"kvm"),
        ("openstack", b"kvm"),
        ("qemu", b"kvm"),
        ("vmware", b"vmware"))
    for name, vm_type in content_vendors_map:
        if name in vendor:
            return vm_type

    return b""


def _get_vm_legacy(root_path):
    """Check if the host is virtualized looking at /proc/cpuinfo content."""
    try:
        cpuinfo = read_text_file(os.path.join(root_path, "proc/cpuinfo"))
    except (IOError, OSError):
        return b""

    if "qemu" in cpuinfo:
        return b"kvm"

    return b""
