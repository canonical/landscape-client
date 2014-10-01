"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import os

from landscape.lib.fs import read_file


def get_vm_info(root_path="/"):
    """
    Return a string with the virtualization type if it's known, an empty string
    otherwise.

    It loops through some possible configurations and return a string with
    the name of the technology being used or None if there's no match
    """
    def join_root_path(path):
        return os.path.join(root_path, path)

    if _is_vm_openvz(root_path):
        return "openvz"
    if _is_vm_xen(root_path):
        return "xen"

    sys_vendor_path = os.path.join(root_path, "sys/class/dmi/id/sys_vendor")
    if os.path.exists(sys_vendor_path):
        return _get_vm_by_vendor(sys_vendor_path)
    else:
        return _get_vm_legacy(root_path)


def get_container_info(path="/run/container_type"):
    """
    Return a string with the type of container the client is running in, if
    any, an empty string otherwise.
    """
    return read_file(path).strip() if os.path.exists(path) else ""


def _is_vm_xen(root_path):
    """Check if the host is virtualized with Xen."""
    xen_paths = [
        os.path.join(root_path, path)
        for path in ("proc/sys/xen", "proc/xen")]

    if filter(os.path.exists, xen_paths):
        return True

    # /sys/bus/xen exists on most machines, but only virtual machines have
    # devices
    sys_xen_path = os.path.join(root_path, "sys/bus/xen/devices")
    return os.path.isdir(sys_xen_path) and os.listdir(sys_xen_path)


def _is_vm_openvz(root_path):
    """Check if the host is virtualized with OpenVZ."""
    return os.path.exists(os.path.join(root_path, "proc/vz"))


def _get_vm_by_vendor(sys_vendor_path):
    """Return the VM type string (possibly empty) based on the vendor."""
    vendor = read_file(sys_vendor_path).lower()
    # Use lower-key string for vendors, since we do case-insentive match.
    content_vendors_map = (
        ("bochs", "kvm"),
        ("google", "gce"),
        ("innotek", "virtualbox"),
        ("microsoft", "hyperv"),
        ("openstack", "kvm"),
        ("qemu", "kvm"),
        ("vmware", "vmware"))
    for name, vm_type in content_vendors_map:
        if name in vendor:
            return vm_type

    return ""


def _get_vm_legacy(root_path):
    """Check if the host is virtualized looking at /proc/cpuinfo content."""
    try:
        cpuinfo = read_file(os.path.join(root_path, "proc/cpuinfo"))
    except (IOError, OSError):
        return ""

    if "qemu" in cpuinfo:
        return "kvm"

    return ""
