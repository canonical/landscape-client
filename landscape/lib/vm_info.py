"""
Network introspection utilities using ioctl and the /proc filesystem.
"""
import os


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

    vz_path = os.path.join(root_path, "proc/vz")
    if os.path.exists(vz_path):
        return "openvz"

    elif filter(os.path.exists, xen_paths):
        return "xen"

    # /sys/bus/xen exists on most machines, but only virtual machines have
    # devices
    sys_xen_path = join_root_path("sys/bus/xen/devices")
    if os.path.isdir(sys_xen_path) and os.listdir(sys_xen_path):
        return "xen"

    cpu_info_path = os.path.join(root_path, "proc/cpuinfo")
    if os.path.exists(cpu_info_path):
        try:
            fd = open(cpu_info_path)
            cpuinfo = fd.read()
            if "QEMU Virtual CPU" in cpuinfo:
                return "kvm"
        finally:
            fd.close()

    sys_vendor_path = os.path.join(root_path, "sys", "class", "dmi", "id",
                                   "sys_vendor")
    if os.path.exists(sys_vendor_path):
        try:
            fd = open(sys_vendor_path)
            file_content = fd.read()
            if "VMware, Inc." in file_content:
                return "vmware"
            elif "Microsoft Corporation" in file_content:
                return "hyperv"
        finally:
            fd.close()

    return ""
