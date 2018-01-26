import mock

from landscape.lib.fs import read_text_file, create_text_file

from landscape.client.deployment import (
    BaseConfiguration, Configuration, get_versioned_persist,
    init_logging)

from landscape.client.tests.helpers import LandscapeTest


class BabbleConfiguration(BaseConfiguration):
    config_section = "babble"
    default_config_filenames = []

    def make_parser(self):
        parser = super(BabbleConfiguration, self).make_parser()
        parser.add_option("--whatever", metavar="STUFF")
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
            mock.ANY, 20, "/somepath", "fooprog", mock.ANY, None)


class BaseConfigurationTest(LandscapeTest):

    def setUp(self):
        super(BaseConfigurationTest, self).setUp()
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
        config = "\n".join(["[%s]" % (section_name,)] +
                           ["%s = %s" % pair for pair in kwargs.items()])
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
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.config, "/etc/landscape/client.conf")

        # The default filename isn't actually used.
        filename = self.config.get_config_filename()
        self.assertIs(filename, None)

    def test_data_directory_default(self):
        """Ensure parse_args sets appropriate data_path default."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.data_path, "/var/lib/landscape/client/")


class ConfigurationTest(LandscapeTest):

    def setUp(self):
        super(ConfigurationTest, self).setUp()

        class MyConfiguration(Configuration):
            default_config_filenames = []

        self.config = MyConfiguration()
        self.parser = self.config.make_parser()

    # logging options

    def test_log_file_option(self):
        """Ensure options.log_dir option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--log-dir", "/var/log/my-awesome-log"])[0]
        self.assertEqual(options.log_dir, "/var/log/my-awesome-log")

    def test_log_level_default(self):
        """Ensure options.log_level default is set within parse_args."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.log_level, "info")

    def test_log_level_option(self):
        """Ensure options.log_level option can be read by parse_args."""
        options = self.parser.parse_args(["--log-level", "debug"])[0]
        self.assertEqual(options.log_level, "debug")

    def test_quiet_option(self):
        """Ensure options.quiet option can be read by parse_args."""
        options = self.parser.parse_args(["--quiet"])[0]
        self.assertEqual(options.quiet, True)

    def test_quiet_default(self):
        """Ensure options.quiet default is set within parse_args."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.quiet, False)

    # other options

    def test_url_option(self):
        """Ensure options.url option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--url", "http://mylandscape/message-system"])[0]
        self.assertEqual(options.url, "http://mylandscape/message-system")

    def test_url_default(self):
        """Ensure parse_args sets appropriate url default."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.url, self.config.DEFAULT_URL)

    def test_ping_url_option(self):
        """Ensure options.ping_url option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--ping-url", "http://mylandscape/ping"])[0]
        self.assertEqual(options.ping_url, "http://mylandscape/ping")

    def test_ping_url_default(self):
        """Ensure parse_args sets appropriate ping_url default."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(
            options.ping_url, "http://landscape.canonical.com/ping")

    def test_ssl_public_key_option(self):
        """Ensure options.ssl_public_key option can be read by parse_args."""
        options = self.parser.parse_args(
            ["--ssl-public-key", "/tmp/somekeyfile.ssl"])[0]
        self.assertEqual(options.ssl_public_key, "/tmp/somekeyfile.ssl")

    def test_ssl_public_key_default(self):
        """Ensure parse_args sets appropriate ssl_public_key default."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.ssl_public_key, None)

    def test_ignore_sigint_option(self):
        """Ensure options.ignore_sigint option can be read by parse_args."""
        options = self.parser.parse_args(["--ignore-sigint"])[0]
        self.assertEqual(options.ignore_sigint, True)

    def test_ignore_sigint_default(self):
        """Ensure options.ignore_sigint default is set within parse_args."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.ignore_sigint, False)

    # hidden options

    def test_clones_default(self):
        """By default, no clones are started."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(0, options.clones)

    def test_clones_option(self):
        """It's possible to specify additional clones to be started."""
        options = self.parser.parse_args(["--clones", "3"])[0]
        self.assertEqual(3, options.clones)

    # properties

    def test_sockets_path(self):
        """
        The L{Configuration.socket_path} property returns the path to the
        socket directory.
        """
        self.assertEqual(
            "/var/lib/landscape/client/sockets",
            self.config.sockets_path)

    def test_annotations_path(self):
        """
        The L{Configuration.annotations_path} property returns the path to the
        annotations directory.
        """
        self.assertEqual(
            "/var/lib/landscape/client/annotations.d",
            self.config.annotations_path)

    def test_juju_filename(self):
        """
        The L{Configuration.juju_filename} property returns the path to the
        juju info file.
        """
        self.assertEqual(
            "/var/lib/landscape/client/juju-info.json",
            self.config.juju_filename)


class GetVersionedPersistTest(LandscapeTest):

    def test_upgrade_service(self):

        class FakeService(object):
            persist_filename = self.makePersistFile(content="")
            service_name = "monitor"

        mock_monitor = mock.Mock()
        with mock.patch.dict("landscape.client.upgraders.UPGRADE_MANAGERS",
                             {"monitor": mock_monitor}):
            persist = get_versioned_persist(FakeService())
            mock_monitor.apply.assert_called_with(persist)
