import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.vm_info import get_vm_info


class VMInfoTest(LandscapeTest):

    sample_kvm_cpuinfo = """
processor	: 0
vendor_id	: GenuineIntel
cpu family	: 6
model		: 2
model name	: QEMU Virtual CPU version 0.14.0
stepping	: 3
cpu MHz		: 2653.112
cache size	: 4096 KB
fpu		: yes
fpu_exception	: yes
cpuid level	: 4
wp		: yes
flags		: fpu de pse tsc msr pae mce cx8 apic sep mtrr pge mca
bogomips	: 5306.22
clflush size	: 64
cache_alignment	: 64
address sizes	: 40 bits physical, 48 bits virtual
power management:
"""

    def test_get_vm_info_empty_when_no_virtualization_is_found(self):
        """
        L{get_vm_info} should be empty when there's no virtualisation.
        """
        root_path = self.makeDir()
        self.assertEqual(u"", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_openvz_when_proc_vz_exists(self):
        """
        L{get_vm_info} should return 'openvz' when /proc/vz exists.
        """
        root_path = self.makeDir()
        proc_path = os.path.join(root_path, "proc")
        self.makeDir(path=proc_path)

        proc_vz_path = os.path.join(proc_path, "vz")
        self.makeFile(path=proc_vz_path, content="foo")

        self.assertEqual("openvz", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_xen_when_proc_sys_xen_exists(self):
        """
        L{get_vm_info} should return 'xen' when /proc/sys/xen exists.
        """
        root_path = self.makeDir()
        proc_path = os.path.join(root_path, "proc")
        self.makeDir(path=proc_path)

        proc_sys_path = os.path.join(proc_path, "sys")
        self.makeDir(path=proc_sys_path)

        proc_sys_xen_path = os.path.join(proc_sys_path, "xen")
        self.makeFile(path=proc_sys_xen_path, content="foo")

        self.assertEqual("xen", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_xen_when_sys_bus_xen_is_non_empty(self):
        """
        L{get_vm_info} should return 'xen' when /sys/bus/xen exists and has
        devices.
        """
        root_path = self.makeDir()
        sys_path = os.path.join(root_path, "sys")
        self.makeDir(path=sys_path)

        sys_bus_path = os.path.join(sys_path, "bus")
        self.makeDir(path=sys_bus_path)

        sys_bus_xen_path = os.path.join(sys_bus_path, "xen")
        self.makeDir(path=sys_bus_xen_path)

        devices_xen_path = os.path.join(sys_bus_xen_path, "devices")
        self.makeDir(path=devices_xen_path)

        foo_devices_path = os.path.join(devices_xen_path, "foo")
        self.makeFile(path=foo_devices_path, content="bar")

        self.assertEqual("xen", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_xen_when_proc_xen_exists(self):
        """
        L{get_vm_info} should return 'xen' when /proc/xen exists.
        """
        root_path = self.makeDir()
        proc_path = os.path.join(root_path, "proc")
        self.makeDir(path=proc_path)

        proc_xen_path = os.path.join(proc_path, "xen")
        self.makeFile(path=proc_xen_path, content="foo")

        self.assertEqual("xen", get_vm_info(root_path=root_path))

    def test_get_vminfo_is_kvm_when_qemu_is_found_in_proc_cpuinfo(self):
        """
        L{get_vm_info} should return 'kvm' when QEMU Virtual CPU is found in
        /proc/cpuinfo.
        """
        root_path = self.makeDir()
        proc_path = os.path.join(root_path, "proc")
        self.makeDir(path=proc_path)

        cpuinfo_path = os.path.join(proc_path, "cpuinfo")
        self.makeFile(path=cpuinfo_path, content=self.sample_kvm_cpuinfo)

        self.assertEqual("kvm", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_empty_when_qemu_is_not_found_in_proc_cpuinfo(self):
        """
        L{get_vm_info} should have an empty string when QEMU Virtual CPU is not
        found in /proc/cpuinfo.
        """
        root_path = self.makeDir()
        proc_path = os.path.join(root_path, "proc")
        self.makeDir(path=proc_path)

        cpuinfo_path = os.path.join(proc_path, "cpuinfo")
        self.makeFile(path=cpuinfo_path, content="foo")
        self.assertEqual("", get_vm_info(root_path=root_path))

    def test_get_vm_info_with_vmware_sys_vendor(self):
        """
        L{get_vm_info} should return "vmware" when we detect the sys_vendor is
        VMware Inc.
        """
        root_path = self.makeDir()
        dmi_path = os.path.join(root_path, "sys", "class", "dmi", "id")
        os.makedirs(dmi_path)
        with file(os.path.join(dmi_path, "sys_vendor"), "w") as fd:
            fd.write("VMware, Inc.")
        self.assertEqual("vmware", get_vm_info(root_path=root_path))

    def test_get_vm_info_is_empty_without_xen_devices(self):
        """
        L{get_vm_info} returns an empty string if the /sys/bus/xen/devices
        directory exists and but doesn't contain any file.
        """
        root_path = self.makeDir()
        sys_path = os.path.join(root_path, "sys")
        self.makeDir(path=sys_path)

        sys_bus_path = os.path.join(sys_path, "bus")
        self.makeDir(path=sys_bus_path)

        sys_bus_xen_path = os.path.join(sys_bus_path, "xen")
        self.makeDir(path=sys_bus_xen_path)

        devices_xen_path = os.path.join(sys_bus_xen_path, "devices")
        self.makeDir(path=devices_xen_path)

        self.assertEqual("", get_vm_info(root_path=root_path))

    def test_get_vm_info_with_microsoft_sys_vendor(self):
        """
        L{get_vm_info} returns "hyperv" if the sys_vendor is Microsoft.
        """
        root_path = self.makeDir()
        dmi_path = os.path.join(root_path, "sys", "class", "dmi", "id")
        os.makedirs(dmi_path)
        with file(os.path.join(dmi_path, "sys_vendor"), "w") as fd:
            fd.write("Microsoft Corporation")
        self.assertEqual("hyperv", get_vm_info(root_path=root_path))
