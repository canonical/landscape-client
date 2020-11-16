import os
import unittest

from landscape.lib import testing
from landscape.lib.vm_info import get_vm_info, get_container_info


class BaseTestCase(testing.FSTestCase, unittest.TestCase):
    pass


class GetVMInfoTest(BaseTestCase):

    def setUp(self):
        super(GetVMInfoTest, self).setUp()
        self.root_path = self.makeDir()
        self.proc_path = self.makeDir(
            path=os.path.join(self.root_path, "proc"))
        self.sys_path = self.makeDir(path=os.path.join(self.root_path, "sys"))
        self.proc_sys_path = self.makeDir(
            path=os.path.join(self.proc_path, "sys"))

    def make_dmi_info(self, name, content):
        """Create /sys/class/dmi/id/<name> with the specified content."""
        dmi_path = os.path.join(self.root_path, "sys/class/dmi/id")
        if not os.path.exists(dmi_path):
            self.makeDir(path=dmi_path)
        self.makeFile(dirname=dmi_path, basename=name, content=content)

    def test_get_vm_info_empty_when_no_virtualization_is_found(self):
        """
        L{get_vm_info} should be empty when there's no virtualisation.
        """
        self.assertEqual(b"", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_openvz_when_proc_vz_exists(self):
        """
        L{get_vm_info} should return 'openvz' when /proc/vz exists.
        """
        proc_vz_path = os.path.join(self.proc_path, "vz")
        self.makeFile(path=proc_vz_path, content="foo")

        self.assertEqual(b"openvz", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_xen_when_sys_bus_xen_is_non_empty(self):
        """
        L{get_vm_info} should return 'xen' when /sys/bus/xen exists and has
        devices.
        """
        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)
        foo_devices_path = os.path.join(devices_xen_path, "foo")
        self.makeFile(path=foo_devices_path, content="bar")

        self.assertEqual(b"xen", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_is_empty_without_xen_devices(self):
        """
        L{get_vm_info} returns an empty string if the /sys/bus/xen/devices
        directory exists but doesn't contain any file.
        """
        devices_xen_path = os.path.join(self.sys_path, "bus/xen/devices")
        self.makeDir(path=devices_xen_path)

        self.assertEqual(b"", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_ec2_sys_vendor(self):
        """
        get_vm_info should return "kvm" when sys_vendor is "Amazon EC2",
        which is the case for C5 instances which are based on KVM.
        """
        self.make_dmi_info("sys_vendor", "Amazon EC2")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_digitalocean_sys_vendor(self):
        """
        get_vm_info should return "kvm" when sys_vendor is "DigitalOcean".
        """
        self.make_dmi_info("sys_vendor", "DigitalOcean")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_kvm_bios_vendor(self):
        """
        get_vm_info should return "kvm" when bios_vendor maps to kvm.
        """
        # DigitalOcean is known to set the bios_vendor on their instances.
        self.make_dmi_info("bios_vendor", "DigitalOcean")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_bochs_chassis_vendor(self):
        """
        get_vm_info should return "kvm" when chassis_vendor is "Bochs".
        """
        # DigitalOcean, AWS and Cloudstack are known to customize sys_vendor
        # and/or bios_vendor.
        self.make_dmi_info("sys_vendor", "Apache Software Foundation")
        self.make_dmi_info("chassis_vendor", "Bochs")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_bochs_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Bochs.
        """
        self.make_dmi_info("sys_vendor", "Bochs")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_openstack_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        Openstack.
        """
        self.make_dmi_info("sys_vendor", "OpenStack Foundation")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_qemu_sys_vendor(self):
        """
        L{get_vm_info} should return "kvm" when we detect the sys_vendor is
        QEMU.
        """
        self.make_dmi_info("sys_vendor", "QEMU")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_vmware_sys_vendor(self):
        """
        L{get_vm_info} should return "vmware" when we detect the sys_vendor is
        VMware Inc.
        """
        self.make_dmi_info("sys_vendor", "VMware, Inc.")
        self.assertEqual(b"vmware", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_virtualbox_sys_vendor(self):
        """
        L{get_vm_info} should return "virtualbox" when we detect the sys_vendor
        is innotek. GmbH.
        """
        self.make_dmi_info("sys_vendor", "innotek GmbH")
        self.assertEqual(b"virtualbox", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_microsoft_sys_vendor(self):
        """
        L{get_vm_info} returns "hyperv" if the sys_vendor is Microsoft.
        """
        self.make_dmi_info("sys_vendor", "Microsoft Corporation")
        self.assertEqual(b"hyperv", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_google_sys_vendor(self):
        """
        L{get_vm_info} returns "gce" if the sys_vendor is Google.
        """
        self.make_dmi_info("sys_vendor", "Google")
        self.assertEqual(b"gce", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_matches_insensitive(self):
        """
        L{get_vm_info} matches the vendor string in a case-insentive way.
        """
        self.make_dmi_info("sys_vendor", "openstack foundation")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_kvm_on_other_architecture(self):
        """
        L{get_vm_info} returns 'kvm', if no sys_vendor is available but the
        model in /proc/cpuinfo contains 'emulated by qemu'.
        """
        cpuinfo_path = os.path.join(self.proc_path, "cpuinfo")
        cpuinfo = (
            "platform	: Some Machine\n"
            "model	: Some CPU (emulated by qemu)\n"
            "machine	: Some Machine (emulated by qemu)\n")
        self.makeFile(path=cpuinfo_path, content=cpuinfo)
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_other_vendor(self):
        """
        L{get_vm_info} should return an empty string when the sys_vendor is
        unknown.
        """
        self.make_dmi_info("sys_vendor", "Some other vendor")
        self.assertEqual(b"", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_kvm_product(self):
        """get_vm_info returns 'kvm', if product_name is 'KVM'."""
        self.make_dmi_info("product_name", "KVM")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))

    def test_get_vm_info_with_rhev(self):
        """get_vm_info returns 'kvm' if running under RHEV Hypervisor."""
        self.make_dmi_info("product_name", "RHEV Hypervisor")
        self.make_dmi_info("sys_vendor", "Red Hat")
        self.assertEqual(b"kvm", get_vm_info(root_path=self.root_path))


class GetContainerInfoTest(BaseTestCase):

    def setUp(self):
        super(GetContainerInfoTest, self).setUp()
        self.run_path = self.makeDir()

    def test_no_container(self):
        """If not running in a container, an empty string is returned."""
        self.assertEqual("", get_container_info(self.run_path))

    def test_in_container_with_container_type_file(self):
        """
        If the /run/container_type file is found, the content is returned as
        container type.
        """
        container_type_file = os.path.join(self.run_path, "container_type")
        self.makeFile(content="lxc", path=container_type_file)
        self.assertEqual("lxc", get_container_info(run_path=self.run_path))

    def test_in_container_with_systemd_container_file(self):
        """
        If the /run/systemd/container file is found, the content is returned as
        container type.
        """
        os.mkdir(os.path.join(self.run_path, "systemd"))
        container_type_file = os.path.join(self.run_path, "systemd/container")
        self.makeFile(content="lxc", path=container_type_file)
        self.assertEqual("lxc", get_container_info(run_path=self.run_path))

    def test_strip_newline(self):
        """The container type doesn't contain newlines."""
        container_type_file = os.path.join(self.run_path, "container_type")
        self.makeFile(content="lxc\n", path=container_type_file)
        self.assertEqual("lxc", get_container_info(run_path=self.run_path))
