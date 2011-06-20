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

    xen_paths = ["proc/sys/xen", "sys/bus/xen", "proc/xen"]
    xen_paths = map(join_root_path, xen_paths)

    vz_path = os.path.join(root_path, "proc/vz")
    if os.path.exists(vz_path):
        return "openvz"

    elif filter(os.path.exists, xen_paths):
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
        finally:
            fd.close()

    return ""
