from datetime import datetime
from unittest import mock
from unittest import TestCase

from landscape.client.deployment import BaseConfiguration
from landscape.client.deployment import Configuration
from landscape.client.deployment import convert_arg_to_bool
from landscape.client.deployment import generate_computer_title
from landscape.client.deployment import get_versioned_persist
from landscape.client.deployment import init_logging
from landscape.client.snap_http import SnapdResponse
from landscape.client.tests.helpers import LandscapeTest
from landscape.lib.fs import create_text_file
from landscape.lib.fs import read_text_file


class BabbleConfiguration(BaseConfiguration):
    config_section = "babble"
    default_config_filenames = []

    def make_parser(self):
        parser = super().make_parser()
        parser.add_argument("--whatever", metavar="STUFF")
        return parser


class LoggingTest(LandscapeTest):
    def test_init_logging_file(self):
        """Check init_logging sets proper logging paths."""

        class MyConfiguration(BaseConfiguration):
            quiet = True
            log_dir = "/somepath"
            log_level = "info"  # 20

        with mock.patch("landscape.lib.logging._init_logging") as mock_log:
            init_logging(MyConfiguration(), "fooprog")

        mock_log.assert_called_once_with(
            mock.ANY,
            20,
            "/somepath",
            "fooprog",
            mock.ANY,
            None,
        )


class BaseConfigurationTest(LandscapeTest):
    def setUp(self):
        super().setUp()
        self.reset_config()

    def reset_config(self, configuration_class=None):
        if not configuration_class:

            class MyConfiguration(BaseConfiguration):
                default_config_filenames = []

            configuration_class = MyConfiguration

        self.config_class = configuration_class
        self.config = configuration_class()
        self.parser = self.config.make_parser()

    def write_config_file(self, **kwargs):
        section_name = kwargs.pop("section_name", "client")
        config = "\n".join(
            [f"[{section_name}]"]
            + [f"{key} = {value}" for key, value in kwargs.items()],
        )
        self.config_filename = self.makeFile(config)
        self.config.default_config_filenames[:] = [self.config_filename]

    # config attributes

    def test_section(self):
        self.assertEqual(BaseConfiguration.config_section, "client")

    def test_get(self):
        self.write_config_file(log_level="file")
        self.config.load([])
        self.assertEqual(self.config.get("log_level"), "file")
        self.assertEqual(self.config.get("random_key"), None)

    def test_clone(self):
        """The BaseConfiguration.clone method clones a configuration."""
        self.write_config_file()
        self.config.load(["--data-path", "/some/path"])
        self.config.foo = "bar"
        config2 = self.config.clone()
        self.assertEqual(self.config.data_path, config2.data_path)
        self.assertEqual("bar", config2.foo)

    # config file

    def test_write_configuration(self):
        self.write_config_file(log_level="debug")
        self.config.log_level = "warning"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = warning")

    def test_load_config_from_option(self):
        """
        Ensure config option of type string shows up in self.config when
        config.load is called.
        """
        filename = self.makeFile("[client]\nhello = world\n")
        self.config.load(["--config", filename])
        self.assertEqual(self.config.hello, "world")

    def test_reload(self):
        """
        Ensure updated options written to config file are surfaced on
        config.reload()
        """
        filename = self.makeFile("[client]\nhello = world1\n")
        self.config.load(["--config", filename])
        create_text_file(filename, "[client]\nhello = world2\n")
        self.config.reload()
        self.assertEqual(self.config.hello, "world2")

    def test_different_config_file_section(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file(section_name="babble", whatever="yay")
        self.config.load([])
        self.assertEqual(self.config.whatever, "yay")

    # CLI options

    def test_config_file_default(self):
        """Ensure parse_args sets appropriate config file default."""
        options = self.parser.parse_args([])
        self.assertEqual(options.config, "/etc/landscape/client.conf")

        # The default filename isn't actually used.
        filename = self.config.get_config_filename()
        self.assertIs(filename, None)

    def test_data_directory_default(self):
        """Ensure parse_args sets appropriate data_path default."""
        options = self.parser.parse_args([])
        self.assertEqual(options.data_path, "/var/lib/landscape/client/")


class ConfigurationTest(LandscapeTest):
    def setUp(self):
        super().setUp()

        class MyConfiguration(Configuration):
            default_config_filenames = []

        self.config = MyConfiguration()
        self.parser = self.config.make_parser()

    # logging options

    def test_log_file_option(self):
        """Ensure options.log_dir option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--log-dir", "/var/log/my-awesome-log"],
        )
        self.assertEqual(options.log_dir, "/var/log/my-awesome-log")

    def test_log_level_default(self):
        """Ensure options.log_level default is set within parse_args."""
        options = self.parser.parse_args([])
        self.assertEqual(options.log_level, "info")

    def test_log_level_option(self):
        """Ensure options.log_level option can be read by parse_args."""
        options = self.parser.parse_args(["--log-level", "debug"])
        self.assertEqual(options.log_level, "debug")

    def test_quiet_option(self):
        """Ensure options.quiet option can be read by parse_args."""
        options = self.parser.parse_args(["--quiet"])
        self.assertEqual(options.quiet, True)

    def test_quiet_default(self):
        """Ensure options.quiet default is set within parse_args."""
        options = self.parser.parse_args([])
        self.assertEqual(options.quiet, False)

    # other options

    def test_url_option(self):
        """Ensure options.url option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--url", "http://mylandscape/message-system"],
        )
        self.assertEqual(options.url, "http://mylandscape/message-system")

    def test_url_default(self):
        """Ensure parse_args sets appropriate url default."""
        options = self.parser.parse_args([])
        self.assertEqual(options.url, self.config.DEFAULT_URL)

    def test_ping_url_option(self):
        """Ensure options.ping_url option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--ping-url", "http://mylandscape/ping"],
        )
        self.assertEqual(options.ping_url, "http://mylandscape/ping")

    def test_ping_url_default(self):
        """Ensure parse_args sets appropriate ping_url default."""
        options = self.parser.parse_args([])
        self.assertEqual(
            options.ping_url,
            "http://landscape.canonical.com/ping",
        )

    def test_ssl_public_key_option(self):
        """Ensure options.ssl_public_key option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--ssl-public-key", "/tmp/somekeyfile.ssl"],
        )
        self.assertEqual(options.ssl_public_key, "/tmp/somekeyfile.ssl")

    def test_ssl_public_key_default(self):
        """Ensure parse_args sets appropriate ssl_public_key default."""
        options = self.parser.parse_args([])
        self.assertEqual(options.ssl_public_key, None)

    def test_ignore_sigint_option(self):
        """Ensure options.ignore_sigint option can be read by parse_args."""
        options = self.parser.parse_args(["--ignore-sigint"])
        self.assertEqual(options.ignore_sigint, True)

    def test_ignore_sigint_default(self):
        """Ensure options.ignore_sigint default is set within parse_args."""
        options = self.parser.parse_args([])
        self.assertEqual(options.ignore_sigint, False)

    # hidden options

    def test_clones_default(self):
        """By default, no clones are started."""
        options = self.parser.parse_args([])
        self.assertEqual(0, options.clones)

    def test_clones_option(self):
        """It's possible to specify additional clones to be started."""
        options = self.parser.parse_args(["--clones", "3"])
        self.assertEqual(3, options.clones)

    # properties

    def test_sockets_path(self):
        """
        The L{Configuration.socket_path} property returns the path to the
        socket directory.
        """
        self.assertEqual(
            "/var/lib/landscape/client/sockets",
            self.config.sockets_path,
        )

    def test_annotations_path(self):
        """
        The L{Configuration.annotations_path} property returns the path to the
        annotations directory.
        """
        self.assertEqual(
            "/var/lib/landscape/client/annotations.d",
            self.config.annotations_path,
        )

    def test_juju_filename(self):
        """
        The L{Configuration.juju_filename} property returns the path to the
        juju info file.
        """
        self.assertEqual(
            "/var/lib/landscape/client/juju-info.json",
            self.config.juju_filename,
        )

    # auto configuration

    @mock.patch("landscape.client.deployment.generate_computer_title")
    @mock.patch("landscape.client.deployment.snap_http")
    def test_auto_configuration(self, mock_snap_http, mock_generate_title):
        """Automatically configures the client."""
        mock_snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"auto-register": {"enabled": True, "configured": False}},
        )
        mock_generate_title.return_value = "ubuntu-123"

        self.assertIsNone(self.config.get("computer_title"))

        self.config.auto_configure()
        self.assertEqual(self.config.get("computer_title"), "ubuntu-123")
        mock_snap_http.set_conf.assert_called_once_with(
            "landscape-client",
            {"auto-register": {"enabled": True, "configured": True}},
        )

    @mock.patch("landscape.client.deployment.snap_http")
    def test_auto_configuration_not_enabled(self, mock_snap_http):
        """The client is not configured."""
        mock_snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"auto-register": {"enabled": False, "configured": False}},
        )

        self.assertIsNone(self.config.get("computer_title"))

        self.config.auto_configure()
        self.assertIsNone(self.config.get("computer_title"))
        mock_snap_http.set_conf.assert_not_called()

    @mock.patch("landscape.client.deployment.snap_http")
    def test_auto_configuration_already_configured(self, mock_snap_http):
        """The client is not re-configured."""
        mock_snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"auto-register": {"enabled": True, "configured": True}},
        )

        self.config.computer_title = "foo-bar"

        self.config.auto_configure()
        self.assertEqual(self.config.get("computer_title"), "foo-bar")
        mock_snap_http.set_conf.assert_not_called()

    @mock.patch("landscape.client.deployment.generate_computer_title")
    @mock.patch("landscape.client.deployment.snap_http")
    def test_auto_configuration_no_title_generated(
        self,
        mock_snap_http,
        mock_generate_title,
    ):
        """The client is not configured."""
        mock_snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"auto-register": {"enabled": True, "configured": False}},
        )
        mock_generate_title.return_value = None

        self.assertIsNone(self.config.get("computer_title"))

        self.config.auto_configure()
        self.assertIsNone(self.config.get("computer_title"))
        mock_snap_http.set_conf.assert_not_called()

    @mock.patch("landscape.client.deployment.generate_computer_title")
    @mock.patch("landscape.client.deployment.snap_http")
    def test_auto_configuration_no_title_generated_retry(
        self,
        mock_snap_http,
        mock_generate_title,
    ):
        """The client is not configured."""
        mock_snap_http.get_conf.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            {"auto-register": {"enabled": True, "configured": False}},
        )
        mock_generate_title.return_value = None

        self.assertIsNone(self.config.get("computer_title"))

        self.config.auto_configure(retry=True, delay=0.01, max_retries=2)
        assert mock_generate_title.call_count == 2
        self.assertIsNone(self.config.get("computer_title"))
        mock_snap_http.set_conf.assert_not_called()


class GetVersionedPersistTest(LandscapeTest):
    def test_upgrade_service(self):
        class FakeService:
            persist_filename = self.makePersistFile(content="")
            service_name = "monitor"

        mock_monitor = mock.Mock()
        with mock.patch.dict(
            "landscape.client.upgraders.UPGRADE_MANAGERS",
            {"monitor": mock_monitor},
        ):
            persist = get_versioned_persist(FakeService())
            mock_monitor.apply.assert_called_with(persist)


class GenerateComputerTitleTest(TestCase):
    """Tests for the `generate_computer_title` function."""

    @mock.patch("landscape.client.deployment.subprocess")
    @mock.patch("landscape.client.deployment.get_active_device_info")
    @mock.patch("landscape.client.deployment.get_fqdn")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title(
        self,
        mock_snap_info,
        mock_fqdn,
        mock_active_device_info,
        mock_subprocess,
    ):
        """Returns a computer title matching `computer-title-pattern`."""
        mock_snap_info.return_value = {
            "serial": "f315cab5-ba74-4d3c-be85-713406455773",
            "model": "generic-classic",
            "brand": "generic",
        }
        mock_fqdn.return_value = "terra"
        mock_active_device_info.return_value = [
            {
                "interface": "wlp108s0",
                "ip_address": "192.168.0.104",
                "mac_address": "5c:80:b6:99:42:8d",
                "broadcast_address": "192.168.0.255",
                "netmask": "255.255.255.0",
            },
        ]
        mock_subprocess.run.return_value.stdout = """
[{
  "id" : "terra",
  "class" : "system",
  "claimed" : true,
  "handle" : "DMI:0002",
  "description" : "Convertible",
  "product" : "HP EliteBook x360 1030 G4 (8TK37UC#ABA)",
  "vendor" : "HP",
  "serial" : "ABCDE"
}]
"""

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${model:8:7}-${serial:0:8}",
                "wait-for-serial-as": True,
                "wait-for-hostname": True,
            },
        )
        self.assertEqual(title, "classic-f315cab5")

    @mock.patch("landscape.client.deployment.debug")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title_wait_for_serial_no_serial_assertion(
        self,
        mock_snap_info,
        mock_debug,
    ):
        """Returns `None`."""
        mock_snap_info.return_value = {}

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${model:8:7}-${serial:0:8}",
                "wait-for-serial-as": True,
                "wait-for-hostname": True,
            },
        )
        self.assertIsNone(title)
        mock_debug.assert_called_once_with(
            "No serial assertion in snap info {}, waiting...",
        )

    @mock.patch("landscape.client.deployment.debug")
    @mock.patch("landscape.client.deployment.get_fqdn")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title_wait_for_hostname(
        self,
        mock_snap_info,
        mock_fqdn,
        mock_debug,
    ):
        """Returns `None`."""
        mock_snap_info.return_value = {
            "serial": "f315cab5-ba74-4d3c-be85-713406455773",
            "model": "generic-classic",
            "brand": "generic",
        }
        mock_fqdn.return_value = "localhost"

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${model:8:7}-${serial:0:8}",
                "wait-for-serial-as": True,
                "wait-for-hostname": True,
            },
        )
        self.assertIsNone(title)
        mock_debug.assert_called_once_with("Waiting for hostname...")

    @mock.patch("landscape.client.deployment.subprocess")
    @mock.patch("landscape.client.deployment.get_active_device_info")
    @mock.patch("landscape.client.deployment.get_fqdn")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title_no_nic(
        self,
        mock_snap_info,
        mock_fqdn,
        mock_active_device_info,
        mock_subprocess,
    ):
        """Returns a title (almost) matching `computer-title-pattern`."""
        mock_snap_info.return_value = {
            "serial": "f315cab5-ba74-4d3c-be85-713406455773",
            "model": "generic-classic",
            "brand": "generic",
        }
        mock_fqdn.return_value = "terra"
        mock_active_device_info.return_value = []
        mock_subprocess.run.return_value.stdout = """
[{
  "id" : "terra",
  "class" : "system",
  "claimed" : true,
  "handle" : "DMI:0002",
  "description" : "Convertible",
  "product" : "HP EliteBook x360 1030 G4 (8TK37UC#ABA)",
  "vendor" : "HP",
  "serial" : "ABCDE"
}]
"""

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${serialno:1}-${ip}",
                "wait-for-serial-as": True,
                "wait-for-hostname": True,
            },
        )
        self.assertEqual(title, "BCDE-")

    @mock.patch("landscape.client.deployment.subprocess")
    @mock.patch("landscape.client.deployment.get_active_device_info")
    @mock.patch("landscape.client.deployment.get_fqdn")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title_with_missing_data(
        self,
        mock_snap_info,
        mock_fqdn,
        mock_active_device_info,
        mock_subprocess,
    ):
        """Returns the default title `hostname`."""
        mock_snap_info.return_value = {}
        mock_fqdn.return_value = "localhost"
        mock_active_device_info.return_value = []
        mock_subprocess.run.return_value.stdout = "[{}]"

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${mac}${serialno}",
                "wait-for-serial-as": False,
                "wait-for-hostname": False,
            },
        )
        self.assertEqual(title, "localhost")

    @mock.patch("landscape.client.deployment.datetime")
    @mock.patch("landscape.client.deployment.subprocess")
    @mock.patch("landscape.client.deployment.get_active_device_info")
    @mock.patch("landscape.client.deployment.get_fqdn")
    @mock.patch("landscape.client.deployment.get_snap_info")
    def test_generate_computer_title_with_date(
        self,
        mock_snap_info,
        mock_fqdn,
        mock_active_device_info,
        mock_subprocess,
        mock_datetime,
    ):
        """Returns a computer title matching `computer-title-pattern`."""
        mock_snap_info.return_value = {}
        mock_fqdn.return_value = "localhost"
        mock_active_device_info.return_value = []
        mock_subprocess.run.return_value.stdout = "[{}]"
        mock_datetime.now.return_value = datetime(2024, 1, 2, 0, 0, 0)

        title = generate_computer_title(
            {
                "enabled": True,
                "configured": False,
                "computer-title-pattern": "${datetime:0:4}-machine",
                "wait-for-serial-as": False,
                "wait-for-hostname": False,
            },
        )
        self.assertEqual(title, "2024-machine")


class ArgConversionTest(LandscapeTest):
    """Tests for `convert_arg_to_bool` function"""

    def test_true_values(self):
        TRUTHY_VALUES = {"true", "yes", "y", "1", "on", "TRUE", "Yes"}
        for t in TRUTHY_VALUES:
            val = convert_arg_to_bool(t)
            self.assertTrue(val)

    def test_false_values(self):
        FALSY_VALUES = {"false", "no", "n", "0", "off", "FALSE", "No"}
        for f in FALSY_VALUES:
            val = convert_arg_to_bool(f)
            self.assertFalse(val)

    @mock.patch("landscape.client.deployment.info")
    def test_invalid_values(self, logging):
        INVALID_VALUES = {"invalid", "truthy", "2", "exit"}
        for i in INVALID_VALUES:
            val = convert_arg_to_bool(i)
            logging.assert_called_with(
                "Error. Invalid boolean provided in config or parameters. "
                + "Defaulting to False.",
            )
            self.assertFalse(val)
