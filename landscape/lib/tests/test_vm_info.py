import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.vm_info import get_vm_info


class VMInfoTest(LandscapeTest):

    sample_cpuinfo = """
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
flags		: {flags}
bogomips	: 5306.22
clflush size	: 64
cache_alignment	: 64
address sizes	: 40 bits physical, 48 bits virtual
power management:
"""

    def setUp(self):
        super(VMInfoTest, self).setUp()
        self.root_path = self.makeDir()
        self.proc_path = self.makeDir(
            path=os.path.join(self.root_path, "proc"))
        self.sys_path = self.makeDir(path=os.path.join(self.root_path, "sys"))
        self.proc_sys_path = self.makeDir(
            path=os.path.join(self.proc_path, "sys"))

    def make_cpuinfo(self, flags=""):
        """Build a sample /proc/cpuinfo with specified processor flags."""
        cpuinfo_path = os.path.join(self.root_path, "proc/cpuinfo")
        self.makeFile(
            path=cpuinfo_path, content=self.sample_cpuinfo.format(flags=flags))

    def test_get_vm_info_empty_when_no_virtualization_is_found(self):
        """
        L{get_vm_info} should be empty when there's no virtualisation.
        """
        self.assertEqual(u"", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_openvz_when_proc_vz_exists(self):
        """
        L{get_vm_info} should return 'openvz' when /proc/vz exists.
        """
        proc_vz_path = os.path.join(self.proc_path, "vz")
        self.makeFile(path=proc_vz_path, content="foo")

        self.assertEqual("openvz", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_xen_when_proc_sys_xen_exists(self):
        """
        L{get_vm_info} should return 'xen' when /proc/sys/xen exists.
        """
        proc_sys_xen_path = os.path.join(self.proc_sys_path, "xen")
        self.makeFile(path=proc_sys_xen_path, content="foo")

        self.assertEqual("xen", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_xen_when_sys_bus_xen_is_non_empty(self):
        """
        L{get_vm_info} should return 'xen' when /sys/bus/xen exists and has
        devices.
        """
        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)
        foo_devices_path = os.path.join(devices_xen_path, "foo")
        self.makeFile(path=foo_devices_path, content="bar")

        self.assertEqual("xen", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_xen_when_proc_xen_exists(self):
        """
        L{get_vm_info} should return 'xen' when /proc/xen exists.
        """
        proc_xen_path = os.path.join(self.proc_path, "xen")
        self.makeFile(path=proc_xen_path, content="foo")

        self.assertEqual("xen", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_empty_when_no_hypervisor_in_proc_cpuinfo(self):
        """
        L{get_vm_info} returns an empty string when the "hypervisor" flag is
        not found in found in /proc/cpuinfo.
        """
        self.make_cpuinfo(flags="fpu vme")

        # The content of sys_vendor is not checked if the "hypervisor" flag is
        # not present.
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"), content="Bochs")

        self.assertEqual("", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_bochs_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Bochs.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"), content="Bochs")

        self.assertEqual("kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_openstack_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Openstack.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"),
            content="OpenStack Foundation")

        self.assertEqual("kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_vmware_sys_vendor(self):
        """
        L{get_vm_info} should return "vmware" when we detect the sys_vendor is
        VMware Inc.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"), content="VMware, Inc.")

        self.assertEqual("vmware", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_empty_without_xen_devices(self):
        """
        L{get_vm_info} returns an empty string if the /sys/bus/xen/devices
        directory exists and but doesn't contain any file.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)

        self.assertEqual("", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_microsoft_sys_vendor(self):
        """
        L{get_vm_info} returns "hyperv" if the sys_vendor is Microsoft.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"),
            content="Microsoft Corporation")
        self.assertEqual("hyperv", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_other_vendor(self):
        """
        L{get_vm_info} should return an empty when the sys_vendor is unknown.
        """
        self.make_cpuinfo(flags="fpu hypervisor vme")

        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"),
            content="Some other vendor")

        self.assertEqual("", get_vm_info(root_path=self.root_path))
