import sys
import os
from optparse import OptionParser

from landscape.deployment import Configuration, get_versioned_persist

from landscape.tests.helpers import LandscapeTest
from landscape.tests.mocker import ANY


class BabbleConfiguration(Configuration):
    config_section = "babble"
    default_config_filenames = []

    def make_parser(self):
        parser = super(BabbleConfiguration, self).make_parser()
        parser.add_option("--whatever", metavar="STUFF")
        return parser


class ConfigurationTest(LandscapeTest):

    def setUp(self):
        super(ConfigurationTest, self).setUp()
        self.reset_config()

    def reset_config(self, configuration_class=None):
        if not configuration_class:

            class MyConfiguration(Configuration):
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

    def test_command_line_with_required_options(self):

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

        sys_exit_mock = self.mocker.replace(sys.exit)
        sys_exit_mock(ANY)
        self.mocker.count(1)
        self.mocker.replay()

        self.config.load([])  # This will call our mocked sys.exit.
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
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = warning")

    def test_write_configuration_with_section(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file(section_name="babble", whatever="yay")
        self.config.whatever = "boo"
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[babble]\nwhatever = boo")

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
        data = open(config_filename).read()
        self.assertEqual(
            data.strip(),
            "[babble]\nwhatever = boo\n\n[goojy]\nunrelated = yes")

    def test_write_on_the_right_default_config_file(self):
        self.write_config_file(log_level="debug")
        config_class = self.config_class
        config_class.default_config_filenames.insert(0, "/non/existent")
        self.config.load([])
        self.config.log_level = "warning"
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = warning")

    def test_dont_write_default_options(self):
        self.write_config_file(log_level="debug")
        self.config.log_level = "info"
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]")

    def test_dont_delete_explicitly_set_default_options(self):
        """
        If the user explicitly sets a configuration option to its default
        value, we shouldn't delete that option from the conf file when we
        write it, just to be nice.
        """
        self.write_config_file(log_level="info")
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = info")

    def test_dont_write_config_option(self):
        self.write_config_file()
        self.config.config = self.config_filename
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]")

    def test_write_command_line_options(self):
        self.write_config_file()
        self.config.load(["--log-level", "warning"])
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = warning")

    def test_write_command_line_precedence(self):
        """Command line options take precedence over config file when writing.
        """
        self.write_config_file(log_level="debug")
        self.config.load(["--log-level", "warning"])
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = warning")

    def test_write_manually_set_precedence(self):
        """Manually set options take precedence over command line when writing.
        """
        self.write_config_file(log_level="debug")
        self.config.load(["--log-level", "warning"])
        self.config.log_level = "error"
        self.config.write()
        data = open(self.config_filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = error")

    def test_write_to_given_config_file(self):
        filename = self.makeFile()
        self.config.load(["--log-level", "warning", "--config", filename],
                         accept_nonexistent_config=True)
        self.config.log_level = "error"
        self.config.write()
        data = open(filename).read()
        self.assertEqual(data.strip(), "[client]\nlog_level = error")

    def test_config_option(self):
        opts = self.parser.parse_args(["--config", "hello.cfg"])[0]
        self.assertEqual(opts.config, "hello.cfg")

    def test_load_config_from_option(self):
        filename = self.makeFile("[client]\nhello = world\n")
        self.config.load(["--config", filename])
        self.assertEqual(self.config.hello, "world")

    def test_load_typed_option_from_file(self):

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

        class MyConfiguration(self.config_class):

            def make_parser(self):
                parser = super(MyConfiguration, self).make_parser()
                parser.add_option("--year", default=1, type="int")
                return parser

        config = MyConfiguration()
        config.load(["--year", "2008"])
        self.assertEqual(config.year, 2008)

    def test_reload(self):
        filename = self.makeFile("[client]\nhello = world1\n")
        self.config.load(["--config", filename])
        open(filename, "w").write("[client]\nhello = world2\n")
        self.config.reload()
        self.assertEqual(self.config.hello, "world2")

    def test_data_directory_option(self):
        opts = self.parser.parse_args(["--data-path", "/opt/hoojy/var/run"])[0]
        self.assertEqual(opts.data_path, "/opt/hoojy/var/run")

    def test_data_directory_default(self):
        opts = self.parser.parse_args([])[0]
        self.assertEqual(opts.data_path, "/var/lib/landscape/client/")

    def test_log_file_option(self):
        opts = self.parser.parse_args(["--log-dir",
                                       "/var/log/my-awesome-log"])[0]
        self.assertEqual(opts.log_dir, "/var/log/my-awesome-log")

    def test_log_level_option(self):
        opts = self.parser.parse_args([])[0]
        self.assertEqual(opts.log_level, "info")
        opts = self.parser.parse_args(["--log-level", "debug"])[0]
        self.assertEqual(opts.log_level, "debug")

    def test_quiet_option(self):
        opts = self.parser.parse_args(["--quiet"])[0]
        self.assertEqual(opts.quiet, True)

    def test_quiet_default(self):
        opts = self.parser.parse_args([])[0]
        self.assertEqual(opts.quiet, False)

    def test_ignore_sigint_option(self):
        opts = self.parser.parse_args(["--ignore-sigint"])[0]
        self.assertEqual(opts.ignore_sigint, True)

    def test_ignore_sigint_default(self):
        opts = self.parser.parse_args([])[0]
        self.assertEqual(opts.ignore_sigint, False)

    def test_get_config_filename_precedence(self):
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

        # If is is readable, than return the first default configuration file.
        os.chmod(default_filename1, 0644)
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
        self.assertEqual(self.config.sockets_path,
                         "/var/lib/landscape/client/sockets")


class GetVersionedPersistTest(LandscapeTest):

    def test_upgrade_service(self):

        class FakeService(object):
            persist_filename = self.makePersistFile(content="")
            service_name = "monitor"

        upgrade_managers = self.mocker.replace(
            "landscape.upgraders.UPGRADE_MANAGERS", passthrough=False)
        upgrade_manager = upgrade_managers["monitor"]
        upgrade_manager.apply(ANY)

        stash = []
        self.mocker.call(stash.append)
        self.mocker.replay()

        persist = get_versioned_persist(FakeService())
        self.assertEqual(stash[0], persist)
