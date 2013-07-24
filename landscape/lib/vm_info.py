"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import os

from landscape.lib.fs import read_file


def get_vm_info(root_path="/"):
    """
    This is a utility that returns the virtualization type

    It loops through some possible configurations and return a string with
    the name of the technology being used or None if there's no match
    """
    def join_root_path(path):
        return os.path.join(root_path, path)

    xen_paths = ["proc/sys/xen", "proc/xen"]
    xen_paths = map(join_root_path, xen_paths)
    vz_path = join_root_path("proc/vz")

    if os.path.exists(vz_path):
        return "openvz"
    elif filter(os.path.exists, xen_paths):
        return "xen"

    # /sys/bus/xen exists on most machines, but only virtual machines have
    # devices
    sys_xen_path = join_root_path("sys/bus/xen/devices")
    if os.path.isdir(sys_xen_path) and os.listdir(sys_xen_path):
        return "xen"

    has_hypervisor_flag = False
    cpu_info_path = join_root_path("proc/cpuinfo")
    if os.path.exists(cpu_info_path):
        content = read_file(cpu_info_path)
        for line in content.split("\n"):
            if line.startswith("flags") and "hypervisor" in line:
                has_hypervisor_flag = True
                break

    # if not has_hypervisor_flag:
    #     return ""

    sys_vendor_path = join_root_path("sys/class/dmi/id/sys_vendor")
    if not os.path.exists(sys_vendor_path):
        return ""

    content = read_file(sys_vendor_path)
    if "VMware, Inc." in content:
        return "vmware"
    elif "Microsoft Corporation" in content:
        return "hyperv"
    elif "Bochs" in content or "OpenStack" in content:
        return "kvm"
    elif "innotek gmbH" in content:
        return "virtualbox"

    return ""
