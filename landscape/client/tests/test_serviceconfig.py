import importlib
import os
import subprocess
from unittest import mock
from unittest import TestCase

import landscape.client.serviceconfig as serviceconfig
from landscape.client.serviceconfig import SNAPCTL
from landscape.client.serviceconfig import SnapdConfig
from landscape.client.serviceconfig import SYSTEMCTL
from landscape.client.serviceconfig import SystemdConfig


class SystemdConfigTestCase(TestCase):
    def setUp(self):
        super().setUp()

        run_patch = mock.patch("subprocess.run")
        self.run_mock = run_patch.start()

        self.addCleanup(mock.patch.stopall)

    def test_set_to_run_on_boot(self):
        SystemdConfig.set_start_on_boot(True)
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "enable", "landscape-client.service", "--quiet"],
            stdout=subprocess.PIPE,
        )

    def test_set_to_not_run_on_boot(self):
        SystemdConfig.set_start_on_boot(False)
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "disable", "landscape-client.service", "--quiet"],
            stdout=subprocess.PIPE,
        )

    def test_configured_to_run(self):
        self.run_mock.return_value = subprocess.CompletedProcess("", 0)

        self.assertTrue(SystemdConfig.is_configured_to_run())
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "is-enabled", "landscape-client.service", "--quiet"],
            stdout=subprocess.PIPE,
        )

    def test_not_configured_to_run(self):
        self.run_mock.return_value = subprocess.CompletedProcess("", 1)

        self.assertFalse(SystemdConfig.is_configured_to_run())
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "is-enabled", "landscape-client.service", "--quiet"],
            stdout=subprocess.PIPE,
        )

    def test_run_landscape(self):
        SystemdConfig.restart_landscape()
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "restart", "landscape-client.service", "--quiet"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_run_landscape_exception(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, "")

        self.assertRaises(
            serviceconfig.ServiceConfigException,
            SystemdConfig.restart_landscape,
        )
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "restart", "landscape-client.service", "--quiet"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_stop_landscape(self):
        SystemdConfig.stop_landscape()
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "stop", "landscape-client.service", "--quiet"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_stop_landscape_exception(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, "")

        self.assertRaises(
            serviceconfig.ServiceConfigException,
            SystemdConfig.stop_landscape,
        )
        self.run_mock.assert_called_once_with(
            [SYSTEMCTL, "stop", "landscape-client.service", "--quiet"],
            check=True,
            stdout=subprocess.PIPE,
        )


class SnapdConfigTestCase(TestCase):
    def setUp(self):
        super().setUp()

        run_patch = mock.patch("subprocess.run")
        self.run_mock = run_patch.start()

        self.addCleanup(mock.patch.stopall)

    def test_set_to_run_on_boot(self):
        SnapdConfig.set_start_on_boot(True)
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "start", "landscape-client", "--enable"],
            stdout=subprocess.PIPE,
        )

    def test_set_to_not_run_on_boot(self):
        SnapdConfig.set_start_on_boot(False)
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "stop", "landscape-client", "--disable"],
            stdout=subprocess.PIPE,
        )

    def test_configured_to_run(self):
        self.run_mock.return_value = subprocess.CompletedProcess(
            "",
            0,
            stdout=(
                "Service           Startup  Current  Notes\n"
                "landscape-client  enabled  active   -\n"
            ),
        )

        self.assertTrue(SnapdConfig.is_configured_to_run())
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "services", "landscape-client"],
            stdout=subprocess.PIPE,
            text=True,
        )

    def test_not_configured_to_run(self):
        self.run_mock.return_value = subprocess.CompletedProcess(
            "",
            0,
            stdout=(
                "Service           Startup   Current   Notes\n"
                "landscape-client  disabled  inactive  -\n"
            ),
        )

        self.assertFalse(SnapdConfig.is_configured_to_run())
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "services", "landscape-client"],
            stdout=subprocess.PIPE,
            text=True,
        )

    def test_run_landscape(self):
        SnapdConfig.restart_landscape()
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "restart", "landscape-client"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_run_landscape_exception(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, "")

        self.assertRaises(
            serviceconfig.ServiceConfigException,
            SnapdConfig.restart_landscape,
        )
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "restart", "landscape-client"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_stop_landscape(self):
        SnapdConfig.stop_landscape()
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "stop", "landscape-client"],
            check=True,
            stdout=subprocess.PIPE,
        )

    def test_stop_landscape_exception(self):
        self.run_mock.side_effect = subprocess.CalledProcessError(1, "")

        self.assertRaises(
            serviceconfig.ServiceConfigException,
            SnapdConfig.stop_landscape,
        )
        self.run_mock.assert_called_once_with(
            [SNAPCTL, "stop", "landscape-client"],
            check=True,
            stdout=subprocess.PIPE,
        )


class ServiceConfigImportTestCase(TestCase):
    """Tests validating we import the appropriate ServiceConfig implementation
    based on configuration.

    N.B.: `importlib.reload` re-binds imports from the module, so this can mess
    with other tests if they rely on identity comparisons, such as in
    exception-catching.
    """

    def test_import_systemd(self):
        os.environ["SNAP_REVISION"] = ""

        importlib.reload(serviceconfig)

        self.assertEqual(
            serviceconfig.ServiceConfig,
            serviceconfig.SystemdConfig,
        )

    def test_import_snapd(self):
        os.environ["SNAP_REVISION"] = "12345"

        importlib.reload(serviceconfig)

        self.assertEqual(
            serviceconfig.ServiceConfig,
            serviceconfig.SnapdConfig,
        )
