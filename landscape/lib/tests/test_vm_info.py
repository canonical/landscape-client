import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.vm_info import get_vm_info


class VMInfoTest(LandscapeTest):

    def setUp(self):
        super(VMInfoTest, self).setUp()
        self.root_path = self.makeDir()
        self.proc_path = self.makeDir(
            path=os.path.join(self.root_path, "proc"))
        self.sys_path = self.makeDir(path=os.path.join(self.root_path, "sys"))
        self.proc_sys_path = self.makeDir(
            path=os.path.join(self.proc_path, "sys"))

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

    def test_get_vm_info_with_bochs_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Bochs.
        """
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
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"), content="VMware, Inc.")

        self.assertEqual("vmware", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_virtualbox_sys_vendor(self):
        """
        L{get_vm_info} should return "virtualbox" when we detect the sys_vendor
        is innotek GmbH.
        """
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"), content="innotek GmbH")

        self.assertEqual("virtualbox", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_empty_without_xen_devices(self):
        """
        L{get_vm_info} returns an empty string if the /sys/bus/xen/devices
        directory exists and but doesn't contain any file.
        """
        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)

        self.assertEqual("", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_microsoft_sys_vendor(self):
        """
        L{get_vm_info} returns "hyperv" if the sys_vendor is Microsoft.
        """
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"),
            content="Microsoft Corporation")
        self.assertEqual("hyperv", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_other_vendor(self):
        """
        L{get_vm_info} should return an empty string when the sys_vendor is
        unknown.
        """
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        self.makeDir(path=dmi_path)
        self.makeFile(
            path=os.path.join(dmi_path, "sys_vendor"),
            content="Some other vendor")

        self.assertEqual("", get_vm_info(root_path=self.root_path))
