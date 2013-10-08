import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.vm_info import get_vm_info, running_in_lxc


class GetVMInfoTest(LandscapeTest):

    def setUp(self):
        super(GetVMInfoTest, self).setUp()
        self.root_path = self.makeDir()
        self.proc_path = self.makeDir(
            path=os.path.join(self.root_path, "proc"))
        self.sys_path = self.makeDir(path=os.path.join(self.root_path, "sys"))
        self.proc_sys_path = self.makeDir(
            path=os.path.join(self.proc_path, "sys"))

    def make_sys_vendor(self, content):
        """Create /sys/class/dmi/id/sys_vendor with the specified content."""
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(dirname=dmi_path, basename="sys_vendor", content=content)

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

    def test_get_vm_info_is_empty_without_xen_devices(self):
        """
        L{get_vm_info} returns an empty string if the /sys/bus/xen/devices
        directory exists but doesn't contain any file.
        """
        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)

        self.assertEqual("", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_bochs_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Bochs.
        """
        self.make_sys_vendor("Bochs")
        self.assertEqual("kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_openstack_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Openstack.
        """
        self.make_sys_vendor("OpenStack Foundation")
        self.assertEqual("kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_vmware_sys_vendor(self):
        """
        L{get_vm_info} should return "vmware" when we detect the sys_vendor is
        VMware Inc.
        """
        self.make_sys_vendor("VMware, Inc.")
        self.assertEqual("vmware", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_virtualbox_sys_vendor(self):
        """
        L{get_vm_info} should return "virtualbox" when we detect the sys_vendor
        is innotek GmbH.
        """
        self.make_sys_vendor("innotek GmbH")
        self.assertEqual("virtualbox", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_microsoft_sys_vendor(self):
        """
        L{get_vm_info} returns "hyperv" if the sys_vendor is Microsoft.
        """
        self.make_sys_vendor("Microsoft Corporation")
        self.assertEqual("hyperv", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_other_vendor(self):
        """
        L{get_vm_info} should return an empty string when the sys_vendor is
        unknown.
        """
        self.make_sys_vendor("Some other vendor")
        self.assertEqual("", get_vm_info(root_path=self.root_path))


class RunningInLXCTest(LandscapeTest):

    def test_no_cgroup_file(self):
        """If the cgroup file doesn't exist, it's not an LXC."""
        self.assertFalse(running_in_lxc(cgroup_file="/not/here"))

    def test_not_in_lxc(self):
        """
        If the cgroup file exists, but there is no mention of LXC, it's not an
        LXC.
        """
        cgroup_file = self.makeFile(content="2:cpu:/")
        self.assertFalse(running_in_lxc(cgroup_file))

    def test_in_lxc(self):
        """
        If the cgroup file exists, and the group name is LXC, it's not an LXC.
        """
        cgroup_file = self.makeFile(content="2:cpu:/lxc/test")
        self.assertTrue(running_in_lxc(cgroup_file))
