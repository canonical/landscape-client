import mock

from landscape.client.tests.helpers import LandscapeTest

from landscape.client.sysvconfig import SystemdConfig, ProcessError


class SystemdConfigTest(LandscapeTest):

    def setUp(self):
        super(SystemdConfigTest, self).setUp()
        patcher = mock.patch("landscape.client.sysvconfig.Popen")
        self.mock_popen = patcher.start()
        self.mock_popen.return_value.wait.return_value = 0
        self.addCleanup(patcher.stop)

    def test_set_to_run_on_boot(self):
        serviceconfig = SystemdConfig()
        serviceconfig.set_start_on_boot(True)
        self.mock_popen.assert_called_once_with(
            ["systemctl", "enable", "landscape-client.service"])

    def test_set_to_not_run_on_boot(self):
        serviceconfig = SystemdConfig()
        serviceconfig.set_start_on_boot(False)
        self.mock_popen.assert_called_once_with(
            ["systemctl", "disable", "landscape-client.service"])

    def test_configured_to_run(self):
        serviceconfig = SystemdConfig()
        self.assertTrue(serviceconfig.is_configured_to_run())
        self.mock_popen.assert_called_once_with(
            ["systemctl", "is-enabled", "landscape-client.service"])

    def test_not_configured_to_run(self):
        self.mock_popen.return_value.wait.return_value = 1
        serviceconfig = SystemdConfig()
        self.assertFalse(serviceconfig.is_configured_to_run())
        self.mock_popen.assert_called_once_with(
            ["systemctl", "is-enabled", "landscape-client.service"])

    def test_run_landscape(self):
        serviceconfig = SystemdConfig()
        serviceconfig.restart_landscape()
        self.mock_popen.assert_called_once_with(
            ["systemctl", "restart", "landscape-client.service"])

    def test_run_landscape_with_error(self):
        self.mock_popen.return_value.wait.return_value = 1
        serviceconfig = SystemdConfig()
        self.assertRaises(ProcessError, serviceconfig.restart_landscape)
        self.mock_popen.assert_called_once_with(
            ["systemctl", "restart", "landscape-client.service"])

    def test_stop_landscape(self):
        serviceconfig = SystemdConfig()
        serviceconfig.stop_landscape()
        self.mock_popen.assert_called_once_with(
            ["systemctl", "stop", "landscape-client.service"])

    def test_stop_landscape_with_error(self):
        self.mock_popen.return_value.wait.return_value = 1
        serviceconfig = SystemdConfig()
        self.assertRaises(ProcessError, serviceconfig.stop_landscape)
        self.mock_popen.assert_called_once_with(
            ["systemctl", "stop", "landscape-client.service"])
