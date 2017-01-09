import os
from optparse import OptionParser
from StringIO import StringIO
from textwrap import dedent

from landscape.lib.fs import read_file, create_file

from landscape.deployment import (
    BaseConfiguration, Configuration, get_versioned_persist)
from landscape.manager.config import ManagerConfiguration

from landscape.tests.helpers import LandscapeTest, LogKeeperHelper
import mock


class BabbleConfiguration(Configuration):
    config_section = "babble"
    default_config_filenames = []

    def make_parser(self):
        parser = super(BabbleConfiguration, self).make_parser()
        parser.add_option("--whatever", metavar="STUFF")
        return parser


class BaseConfigurationTest(LandscapeTest):

    def test_load_not_found_default_accept_missing(self):
        """
        C{config.load} doesn't exit the process if the default config file
        is not found and C{accept_nonexistent_default_config} is C{True}.
        """
        class MyConfiguration(BaseConfiguration):
            default_config_filenames = ["/not/here"]

        config = MyConfiguration()
        result = config.load([], accept_nonexistent_default_config=True)
        self.assertIs(result, None)

    def test_load_not_found_accept_missing(self):
        """
        C{config.load} exits the process if the specified config file
        is not found and C{accept_nonexistent_default_config} is C{True}.
        """
        class MyConfiguration(BaseConfiguration):
            default_config_filenames = []

        config = MyConfiguration()
        filename = "/not/here"
        error = self.assertRaises(
            SystemExit, config.load, ["--config", filename],
            accept_nonexistent_default_config=True)
        self.assertEqual(
            "error: config file %s can't be read" % filename, str(error))


class ConfigurationTest(LandscapeTest):

    helpers = [LogKeeperHelper]

    def setUp(self):
        super(ConfigurationTest, self).setUp()
        self.reset_config()

    def reset_config(self, configuration_class=None):
        if not configuration_class:

            class MyConfiguration(ManagerConfiguration):
                default_config_filenames = []
            configuration_class = MyConfiguration

        self.config_class = configuration_class
        self.config = configuration_class()
        self.parser = self.config.make_parser()

    def test_get(self):
        self.write_config_file(log_level="file")
        self.config.load([])
        self.assertEqual(self.config.get("log_level"), "file")
        self.assertEqual(self.config.get("random_key"), None)

    def test_get_config_object(self):
        """
        Calling L{get_config_object} returns a L{ConfigObj} bound to the
        correct file and with its options set in the manor we expect.
        """
        config_obj = self.config._get_config_object()
        self.assertEqual(self.config.get_config_filename(),
                         config_obj.filename)
        self.assertFalse(config_obj.list_values)

    def test_get_config_object_with_alternative_config(self):
        """
        Calling L{get_config_object} with a the L{alternative_config} parameter
        set, this source is used instead of calling through to
        L{get_config_filename}.
        """
        config_obj = self.config._get_config_object(
            alternative_config=StringIO("[client]\nlog_level = error\n"))
        self.assertEqual(None, config_obj.filename)

    def write_config_file(self, **kwargs):
        section_name = kwargs.pop("section_name", "client")
        config = "\n".join(["[%s]" % (section_name,)] +
                           ["%s = %s" % pair for pair in kwargs.items()])
        self.config_filename = self.makeFile(config)
        self.config.default_config_filenames[:] = [self.config_filename]

    def test_command_line_has_precedence(self):
        self.write_config_file(log_level="file")
        self.config.load(["--log-level", "command line"])
        self.assertEqual(self.config.log_level, "command line")

    def test_command_line_option_without_default(self):

        class MyConfiguration(Configuration):

            def make_parser(self):
                parser = OptionParser()
                # Keep the dash in the option name to ensure it works.
                parser.add_option("--foo-bar")
                return parser

        self.assertEqual(MyConfiguration().foo_bar, None)

    @mock.patch("sys.exit")
    def test_command_line_with_required_options(self, mock_exit):

        class MyConfiguration(Configuration):
            required_options = ("foo_bar",)
            config = None

            def make_parser(self):
                parser = super(MyConfiguration, self).make_parser()
                # Keep the dash in the option name to ensure it works.
                parser.add_option("--foo-bar", metavar="NAME")
                return parser
        self.reset_config(configuration_class=MyConfiguration)
        self.write_config_file()

        self.config.load([])  # This will call our mocked sys.exit.
        mock_exit.assert_called_once_with(mock.ANY)

        self.config.load(["--foo-bar", "ooga"])
        self.assertEqual(self.config.foo_bar, "ooga")

    def test_command_line_with_unsaved_options(self):

        class MyConfiguration(Configuration):
            unsaved_options = ("foo_bar",)
            config = None

            def make_parser(self):
                parser = super(MyConfiguration, self).make_parser()
                # Keep the dash in the option name to ensure it works.
                parser.add_option("--foo-bar", metavar="NAME")
                return parser

        self.reset_config(configuration_class=MyConfiguration)
        self.write_config_file()

        self.config.load(["--foo-bar", "ooga"])
        self.assertEqual(self.config.foo_bar, "ooga")
        self.config.write()

        self.config.load([])
        self.assertEqual(self.config.foo_bar, None)

    def test_config_file_has_precedence_over_default(self):
        self.write_config_file(log_level="file")
        self.config.load([])
        self.assertEqual(self.config.log_level, "file")

    def test_different_config_file_section(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file(section_name="babble", whatever="yay")
        self.config.load([])
        self.assertEqual(self.config.whatever, "yay")

    def test_no_section_available(self):
        config_filename = self.makeFile("")

        class MyConfiguration(Configuration):
            config_section = "nonexistent"
            default_config_filenames = (config_filename,)

        self.reset_config(configuration_class=MyConfiguration)
        self.config.load([])

    def test_write_configuration(self):
        self.write_config_file(log_level="debug")
        self.config.log_level = "warning"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = warning")

    def test_write_configuration_with_section(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file(section_name="babble", whatever="yay")
        self.config.whatever = "boo"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[babble]\nwhatever = boo")

    def test_write_unrelated_configuration_back(self):
        """
        If a configuration file has a section that isn't processed by a
        particular configuration object, that unrelated configuration section
        will be maintained even when written back.
        """
        self.reset_config(configuration_class=BabbleConfiguration)
        config = "[babble]\nwhatever = zoot\n[goojy]\nunrelated = yes"
        config_filename = self.makeFile(config)
        self.config.load_configuration_file(config_filename)
        self.config.whatever = "boo"
        self.config.write()
        data = read_file(config_filename)
        self.assertConfigEqual(
            data,
            "[babble]\nwhatever = boo\n\n[goojy]\nunrelated = yes")

    def test_write_on_the_right_default_config_file(self):
        self.write_config_file(log_level="debug")
        config_class = self.config_class
        config_class.default_config_filenames.insert(0, "/non/existent")
        self.config.load([])
        self.config.log_level = "warning"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = warning\n")

    def test_write_empty_list_values_instead_of_double_quotes(self):
        """
        Since list values are strings, an empty string such as C{""} will be
        written to the config file as an option with a empty value instead of
        C{""}.
        """
        self.write_config_file(include_manager_plugins="ScriptExecution")
        self.config.load([])
        self.config.include_manager_plugins = ""
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\ninclude_manager_plugins = \n")

    def test_dont_write_config_specified_default_options(self):
        """
        Don't write options to the file if the value exactly matches the
        default and the value already existed in the original config file.
        """
        self.write_config_file(log_level="debug")
        self.config.log_level = "info"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]")

    def test_dont_write_unspecified_default_options(self):
        """
        Don't write options to the file if the value exactly matches the
        default and the value did not exist in the original config file.
        """
        self.write_config_file()
        self.config.log_level = "info"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]")

    def test_dont_write_client_section_default_options(self):
        """
        Don't write options to the file if they exactly match the default and
        didn't already exist in the file.
        """
        self.write_config_file(log_level="debug")
        self.config.log_level = "info"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]")

    def test_do_write_preexisting_default_options(self):
        """
        If the value of an option matches the default, but the option was
        already written in the file, then write it back to the file.
        """
        config = "[client]\nlog_level = info\n"
        config_filename = self.makeFile(config)
        self.config.load_configuration_file(config_filename)
        self.config.log_level = "info"
        self.config.write()
        data = read_file(config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = info\n")

    def test_dont_delete_explicitly_set_default_options(self):
        """
        If the user explicitly sets a configuration option to its default
        value, we shouldn't delete that option from the conf file when we
        write it, just to be nice.
        """
        self.write_config_file(log_level="info")
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = info")

    def test_dont_write_config_option(self):
        self.write_config_file()
        self.config.config = self.config_filename
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]")

    def test_write_command_line_options(self):
        self.write_config_file()
        self.config.load(["--log-level", "warning"])
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = warning\n")

    def test_write_command_line_precedence(self):
        """Command line options take precedence over config file when writing.
        """
        self.write_config_file(log_level="debug")
        self.config.load(["--log-level", "warning"])
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = warning\n")

    def test_write_manually_set_precedence(self):
        """Manually set options take precedence over command line when writing.
        """
        self.write_config_file(log_level="debug")
        self.config.load(["--log-level", "warning"])
        self.config.log_level = "error"
        self.config.write()
        data = read_file(self.config_filename)
        self.assertConfigEqual(data, "[client]\nlog_level = error\n")

    def test_write_to_given_config_file(self):
        filename = self.makeFile(content="")
        self.config.load(
            ["--log-level", "warning", "--config", filename])
        self.config.log_level = "error"
        self.config.write()
        data = read_file(filename)
        self.assertConfigEqual(data, "[client]\nlog_level = error\n")

    def test_comments_are_maintained(self):
        """
        When we write an updated config file, comments that existed previously
        are maintained.
        """
        config = "[client]\n# Comment 1\nlog_level = file\n#Comment 2\n"
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.config.log_level = "error"
        self.config.write()
        new_config = read_file(filename)
        self.assertConfigEqual(
            new_config,
            "[client]\n# Comment 1\nlog_level = error\n#Comment 2\n")

    def test_config_option(self):
        options = self.parser.parse_args(["--config", "hello.cfg"])[0]
        self.assertEqual(options.config, "hello.cfg")

    def test_load_config_from_option(self):
        """
        Ensure config option of type string shows up in self.config when
        config.load is called.
        """
        filename = self.makeFile("[client]\nhello = world\n")
        self.config.load(["--config", filename])
        self.assertEqual(self.config.hello, "world")

    def test_load_typed_option_from_file(self):
        """
        Ensure config option of type int shows up in self.config when
        config.load is called.
        """

        class MyConfiguration(self.config_class):

            def make_parser(self):
                parser = super(MyConfiguration, self).make_parser()
                parser.add_option("--year", default=1, type="int")
                return parser

        filename = self.makeFile("[client]\nyear = 2008\n")
        config = MyConfiguration()
        config.load(["--config", filename])
        self.assertEqual(config.year, 2008)

    def test_load_typed_option_from_command_line(self):
        """
        Ensure command line config option of type int shows up in self.config
        when config.load is called.
        """

        class MyConfiguration(self.config_class):

            def make_parser(self):
                parser = super(MyConfiguration, self).make_parser()
                parser.add_option("--year", default=1, type="int")
                return parser

        self.write_config_file()
        config = MyConfiguration()
        config.load(["--year", "2008"])
        self.assertEqual(config.year, 2008)

    def test_reload(self):
        """
        Ensure updated options written to config file are surfaced on
        config.reload()
        """
        filename = self.makeFile("[client]\nhello = world1\n")
        self.config.load(["--config", filename])
        create_file(filename, "[client]\nhello = world2\n")
        self.config.reload()
        self.assertEqual(self.config.hello, "world2")

    def test_load_cannot_read(self):
        """
        C{config.load} exits the process if the specific config file can't be
        read because of permission reasons.
        """
        filename = self.makeFile("[client]\nhello = world1\n")
        os.chmod(filename, 0)
        error = self.assertRaises(
            SystemExit, self.config.load, ["--config", filename])
        self.assertEqual(
            "error: config file %s can't be read" % filename, str(error))

    def test_load_not_found(self):
        """
        C{config.load} exits the process if the specified config file is not
        found.
        """
        filename = "/not/here"
        error = self.assertRaises(
            SystemExit, self.config.load, ["--config", filename])
        self.assertEqual(
            "error: config file %s can't be read" % filename, str(error))

    def test_load_cannot_read_default(self):
        """
        C{config.load} exits the process if the default config file can't be
        read because of permission reasons.
        """
        self.write_config_file()
        [default] = self.config.default_config_filenames
        os.chmod(default, 0)
        error = self.assertRaises(SystemExit, self.config.load, [])
        self.assertEqual(
            "error: config file %s can't be read" % default, str(error))

    def test_load_not_found_default(self):
        """
        C{config.load} exits the process if the default config file is not
        found.
        """
        [default] = self.config.default_config_filenames[:] = ["/not/here"]
        error = self.assertRaises(SystemExit, self.config.load, [])
        self.assertEqual(
            "error: config file %s can't be read" % default, str(error))

    def test_load_cannot_read_many_defaults(self):
        """
        C{config.load} exits the process if none of the default config files
        exists and can be read.
        """
        default1 = self.makeFile("")
        default2 = self.makeFile("")
        os.chmod(default1, 0)
        os.unlink(default2)
        self.config.default_config_filenames[:] = [default1, default2]

        error = self.assertRaises(SystemExit, self.config.load, [])
        self.assertEqual("error: no config file could be read", str(error))

    def test_data_directory_option(self):
        """Ensure options.data_path option can be read by parse_args."""
        options = self.parser.parse_args(["--data-path",
                                          "/opt/hoojy/var/run"])[0]
        self.assertEqual(options.data_path, "/opt/hoojy/var/run")

    def test_data_directory_default(self):
        """Ensure parse_args sets appropriate data_path default."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.data_path, "/var/lib/landscape/client/")

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

    def test_clones_default(self):
        """By default, no clones are started."""
        self.write_config_file()
        options = self.parser.parse_args([])[0]
        self.assertEqual(0, options.clones)

    def test_clones_option(self):
        """It's possible to specify additional clones to be started."""
        options = self.parser.parse_args(["--clones", "3"])[0]
        self.assertEqual(3, options.clones)

    def test_ignore_sigint_option(self):
        """Ensure options.ignore_sigint option can be read by parse_args."""
        options = self.parser.parse_args(["--ignore-sigint"])[0]
        self.assertEqual(options.ignore_sigint, True)

    def test_ignore_sigint_default(self):
        """Ensure options.ignore_sigint default is set within parse_args."""
        options = self.parser.parse_args([])[0]
        self.assertEqual(options.ignore_sigint, False)

    def test_get_config_filename_precedence(self):
        """
        Validate landscape-client configuration file load precedence. The
        client config should return the first readable configuration files in
        the default_config_filenames list if no config option was requested.

        If a specific config file is requested, use this instead of defaults.

        If a cmdline --config option is specified this should take precedence
        over either of the former options.
        """
        default_filename1 = self.makeFile("")
        default_filename2 = self.makeFile("")
        explicit_filename = self.makeFile("")
        loaded_filename = self.makeFile("")
        self.config.default_config_filenames[:] = [default_filename1,
                                                   default_filename2]

        # If nothing else is set, and the first configuration file
        # isn't readable, return the second default file.
        os.chmod(default_filename1, 0)
        self.assertEqual(self.config.get_config_filename(),
                         default_filename2)

        # If it is readable, than return the first default configuration file.
        os.chmod(default_filename1, 0o644)
        self.assertEqual(self.config.get_config_filename(),
                         default_filename1)

        # Unless another file was explicitly loaded before, in which
        # case return the loaded filename.
        self.config.load_configuration_file(loaded_filename)
        self.assertEqual(self.config.get_config_filename(),
                         loaded_filename)

        # Except in the case where a configuration file was explicitly
        # requested through the command line or something.  In this case,
        # this is the highest precedence.
        self.config.config = explicit_filename
        self.assertEqual(self.config.get_config_filename(),
                         explicit_filename)

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

    def test_clone(self):
        """The L{Configuration.clone} method clones a configuration."""
        self.write_config_file()
        self.config.load(["--data-path", "/some/path"])
        self.config.foo = "bar"
        config2 = self.config.clone()
        self.assertEqual(self.config.data_path, config2.data_path)
        self.assertEqual("bar", config2.foo)

    def test_duplicate_key(self):
        """
        Duplicate keys in the config file shouldn't result in a fatal error,
        but the first defined value should be used.
        """
        config = dedent("""
        [client]
        computer_title = frog
        computer_title = flag
        """)
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.assertEqual("frog", self.config.computer_title)
        self.assertIn("WARNING: Duplicate keyword name at line 4.",
                      self.logfile.getvalue())

    def test_triplicate_key(self):
        """
        Triplicate keys in the config file shouldn't result in a fatal error,
        but the first defined value should be used.
        """
        config = dedent("""
        [client]
        computer_title = frog
        computer_title = flag
        computer_title = flop
        """)
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.assertEqual("frog", self.config.computer_title)
        logged = self.logfile.getvalue()
        self.assertIn("WARNING: Parsing failed with several errors.",
                      logged)
        self.assertIn("First error at line 4.", logged)

    def test_config_values_after_fault_are_still_read(self):
        """
        Values that appear after the point in a configuration file where a
        parsing error occurs are correctly parsed.
        """
        config = dedent("""
        [client]
        computer_title = frog
        computer_title = flag
        log_level = debug
        """)
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.assertEqual("debug", self.config.log_level)
        self.assertIn("WARNING: Duplicate keyword name at line 4.",
                      self.logfile.getvalue())


class GetVersionedPersistTest(LandscapeTest):

    def test_upgrade_service(self):

        class FakeService(object):
            persist_filename = self.makePersistFile(content="")
            service_name = "monitor"

        mock_monitor = mock.Mock()
        with mock.patch.dict("landscape.upgraders.UPGRADE_MANAGERS",
                             {"monitor": mock_monitor}):
            persist = get_versioned_persist(FakeService())
            mock_monitor.apply.assert_called_with(persist)
