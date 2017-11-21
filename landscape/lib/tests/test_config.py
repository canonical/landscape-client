from optparse import OptionParser
from textwrap import dedent
import io
import mock
import os
import os.path
import sys
import unittest

from landscape.lib.fs import read_text_file, create_text_file
from landscape.lib.testing import (
        HelperTestCase, ConfigTestCase, LogKeeperHelper)

from landscape.lib.config import BaseConfiguration, get_bindir


class BabbleConfiguration(BaseConfiguration):
    config_section = "babble"
    default_config_filenames = []

    def make_parser(self):
        parser = super(BabbleConfiguration, self).make_parser()
        parser.add_option("--whatever", metavar="STUFF")
        return parser


def cfg_class(section=None, **defaults):
    class MyConfiguration(BaseConfiguration):
        config_section = section or "my-config"
        default_config_filenames = []

        def make_parser(self):
            parser = super(MyConfiguration, self).make_parser()
            for name, value in defaults.items():
                name = name.replace("_", "-")
                parser.add_option("--" + name, default=value)
            return parser

    return MyConfiguration


class BaseConfigurationTest(ConfigTestCase, HelperTestCase, unittest.TestCase):

    helpers = [LogKeeperHelper]

    def setUp(self):
        super(BaseConfigurationTest, self).setUp()
        self.reset_config(cfg_class())

    def reset_config(self, configuration_class):
        self.config_class = configuration_class
        self.config = configuration_class()
        self.parser = self.config.make_parser()

    def write_config_file(self, **kwargs):
        section_name = kwargs.pop("section_name",
                                  self.config_class.config_section)
        config = "\n".join(["[%s]" % (section_name,)] +
                           ["%s = %s" % pair for pair in kwargs.items()])
        self.config_filename = self.makeFile(config)
        self.config.default_config_filenames[:] = [self.config_filename]

    # config attributes

    def test_get(self):
        self.write_config_file(spam="eggs")
        self.config.load([])
        self.assertEqual(self.config.get("spam"), "eggs")
        self.assertEqual(self.config.get("random_key"), None)

    def test_clone(self):
        """The Configuration.clone method clones a configuration."""
        self.write_config_file()
        self.config.load(["--data-path", "/some/path"])
        self.config.foo = "bar"
        config2 = self.config.clone()
        self.assertEqual(self.config.data_path, config2.data_path)
        self.assertEqual("bar", config2.foo)

    # precedence

    def test_command_line_has_precedence(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file(whatever="spam")
        self.config.load(["--whatever", "command line"])
        self.assertEqual(self.config.whatever, "command line")

    def test_config_file_has_precedence_over_default(self):
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file(whatever="eggs")
        self.config.load([])
        self.assertEqual(self.config.whatever, "eggs")

    def test_write_command_line_precedence(self):
        """
        Command line options take precedence over config file when writing.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file(whatever="eggs")
        self.config.load(["--whatever", "ham"])
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = ham\n")

    def test_write_manually_set_precedence(self):
        """
        Manually set options take precedence over command line when writing.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file(whatever="eggs")
        self.config.load(["--whatever", "42"])
        self.config.whatever = "ham"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = ham\n")

    def test_get_config_filename_precedence(self):
        """
        Validate configuration file load precedence. The
        config should return the first readable configuration files in
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

    # ConfigObj

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
        Calling get_config_object with the alternative_config parameter
        set, this source is used instead of calling through to
        get_config_filename.
        """
        config_obj = self.config._get_config_object(
            alternative_config=io.StringIO(u"[my-config]\nwhatever = error\n"))
        self.assertEqual(None, config_obj.filename)

    # CLI options

    def test_command_line_option_without_default(self):
        class MyConfiguration(BaseConfiguration):
            def make_parser(self):
                parser = OptionParser()
                # Keep the dash in the option name to ensure it works.
                parser.add_option("--foo-bar")
                return parser

        self.assertEqual(MyConfiguration().foo_bar, None)

    @mock.patch("sys.exit")
    def test_command_line_with_required_options(self, mock_exit):
        self.reset_config(cfg_class(foo_bar=None))
        self.config_class.required_options = ("foo_bar",)
        self.config_class.config = None
        self.write_config_file()

        self.config.load([])  # This will call our mocked sys.exit.
        mock_exit.assert_called_once_with(mock.ANY)

        self.config.load(["--foo-bar", "ooga"])
        self.assertEqual(self.config.foo_bar, "ooga")

    def test_command_line_with_unsaved_options(self):
        self.reset_config(cfg_class(foo_bar=None))
        self.config_class.unsaved_options = ("foo_bar",)
        self.config_class.config = None
        self.write_config_file()

        self.config.load(["--foo-bar", "ooga"])
        self.assertEqual(self.config.foo_bar, "ooga")
        self.config.write()

        self.config.load([])
        self.assertEqual(self.config.foo_bar, None)

    # --config

    def test_config_option(self):
        options = self.parser.parse_args(["--config", "hello.cfg"])[0]
        self.assertEqual(options.config, "hello.cfg")

    def test_config_file_default(self):
        """Ensure parse_args sets appropriate config file default."""
        options = self.parser.parse_args([])[0]
        self.assertIs(options.config, None)

        parser = BaseConfiguration().make_parser(
                cfgfile="spam.conf",
                datadir="/tmp/spam/data",
                )
        options = parser.parse_args([])[0]
        self.assertEqual(options.config, "spam.conf")

    def test_load_config_from_option(self):
        """
        Ensure config option of type string shows up in self.config when
        config.load is called.
        """
        filename = self.makeFile("[my-config]\nhello = world\n")
        self.config.load(["--config", filename])
        self.assertEqual(self.config.hello, "world")

    def test_write_to_given_config_file(self):
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        filename = self.makeFile(content="")
        self.config.load(["--whatever", "eggs",
                          "--config", filename])
        self.config.whatever = "ham"
        self.config.write()
        data = read_text_file(filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = ham\n")

    # --data-path

    def test_data_directory_option(self):
        """Ensure options.data_path option can be read by parse_args."""
        options = self.parser.parse_args(["--data-path",
                                          "/opt/hoojy/var/run"])[0]
        self.assertEqual(options.data_path, "/opt/hoojy/var/run")

    def test_data_directory_default(self):
        """Ensure parse_args sets appropriate data_path default."""
        options = self.parser.parse_args([])[0]
        self.assertIs(options.data_path, None)

        parser = BaseConfiguration().make_parser(
                cfgfile="spam.conf",
                datadir="/tmp/spam/data",
                )
        options = parser.parse_args([])[0]
        self.assertEqual(options.data_path, "/tmp/spam/data")

    # loading

    def test_reload(self):
        """
        Ensure updated options written to config file are surfaced on
        config.reload()
        """
        filename = self.makeFile("[my-config]\nhello = world1\n")
        self.config.load(["--config", filename])
        create_text_file(filename, "[my-config]\nhello = world2\n")
        self.config.reload()
        self.assertEqual(self.config.hello, "world2")

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

        filename = self.makeFile("[my-config]\nyear = 2008\n")
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

    def test_load_no_section_available(self):
        self.config_class.default_config_filenames = (
            self.makeFile(""),
            )
        self.reset_config(self.config_class)
        self.config.load([])

    def test_config_values_after_fault_are_still_read(self):
        """
        Values that appear after the point in a configuration file where a
        parsing error occurs are correctly parsed.
        """
        filename = self.makeFile(dedent("""
        [my-config]
        computer_title = frog
        computer_title = flag
        whatever = spam
        """))
        self.config.load_configuration_file(filename)
        self.assertEqual(self.config.whatever, "spam")
        self.assertIn("WARNING: Duplicate keyword name at line 4.",
                      self.logfile.getvalue())

    def test_duplicate_key(self):
        """
        Duplicate keys in the config file shouldn't result in a fatal error,
        but the first defined value should be used.
        """
        config = dedent("""
        [my-config]
        computer_title = frog
        computer_title = flag
        """)
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.assertEqual(self.config.computer_title, "frog")
        self.assertIn("WARNING: Duplicate keyword name at line 4.",
                      self.logfile.getvalue())

    def test_triplicate_key(self):
        """
        Triplicate keys in the config file shouldn't result in a fatal error,
        but the first defined value should be used.
        """
        config = dedent("""
        [my-config]
        computer_title = frog
        computer_title = flag
        computer_title = flop
        """)
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.assertEqual(self.config.computer_title, "frog")
        logged = self.logfile.getvalue()
        self.assertIn("WARNING: Parsing failed with several errors.",
                      logged)
        self.assertIn("First error at line 4.", logged)

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
        with self.assertRaises(SystemExit) as cm:
            config.load(["--config", filename],
                        accept_nonexistent_default_config=True)
        self.assertEqual(str(cm.exception),
                         "error: config file %s can't be read" % filename)

    def test_load_cannot_read(self):
        """
        C{config.load} exits the process if the specific config file can't be
        read because of permission reasons.
        """
        filename = self.makeFile("[my-config]\nhello = world1\n")
        os.chmod(filename, 0)
        with self.assertRaises(SystemExit) as cm:
            self.config.load(["--config", filename])
        self.assertEqual(str(cm.exception),
                         "error: config file %s can't be read" % filename)

    def test_load_not_found(self):
        """
        C{config.load} exits the process if the specified config file is not
        found.
        """
        filename = "/not/here"
        with self.assertRaises(SystemExit) as cm:
            self.config.load(["--config", filename])
        self.assertEqual(str(cm.exception),
                         "error: config file %s can't be read" % filename)

    def test_load_cannot_read_default(self):
        """
        C{config.load} exits the process if the default config file can't be
        read because of permission reasons.
        """
        self.write_config_file()
        [default] = self.config.default_config_filenames
        os.chmod(default, 0)
        with self.assertRaises(SystemExit) as cm:
            self.config.load([])
        self.assertEqual(str(cm.exception),
                         "error: config file %s can't be read" % default)

    def test_load_not_found_default(self):
        """
        C{config.load} exits the process if the default config file is not
        found.
        """
        [default] = self.config.default_config_filenames[:] = ["/not/here"]
        with self.assertRaises(SystemExit) as cm:
            self.config.load([])
        self.assertEqual(str(cm.exception),
                         "error: config file %s can't be read" % default)

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

        with self.assertRaises(SystemExit) as cm:
            self.config.load([])
        self.assertEqual(str(cm.exception),
                         "error: no config file could be read")

    # saving

    def test_write_new_file(self):
        self.config_filename = self.makeFile("")
        os.unlink(self.config_filename)
        self.config.default_config_filenames[:] = [self.config_filename]
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = eggs")

    def test_write_existing_empty_file(self):
        self.config_filename = self.makeFile("")
        self.config.default_config_filenames[:] = [self.config_filename]
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = eggs")

    def test_write_existing_file(self):
        self.config_filename = self.makeFile(
                "\n[other]\nfoo = bar\n[again]\nx = y\n")
        self.config.default_config_filenames[:] = [self.config_filename]
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, ("[other]\nfoo = bar\n"
                                      "[again]\nx = y\n"
                                      "[my-config]\nwhatever = eggs"))

    def test_write_existing_section(self):
        self.write_config_file()
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = eggs")

    def test_write_existing_value(self):
        self.write_config_file(whatever="spam")
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = eggs")

    def test_write_unrelated_configuration_back(self):
        """
        If a configuration file has a section that isn't processed by a
        particular configuration object, that unrelated configuration section
        will be maintained even when written back.
        """
        config = "[my-config]\nwhatever = zoot\n[goojy]\nunrelated = yes"
        config_filename = self.makeFile(config)
        self.config.load_configuration_file(config_filename)
        self.config.whatever = "boo"
        self.config.write()
        data = read_text_file(config_filename)
        self.assertConfigEqual(
            data,
            "[my-config]\nwhatever = boo\n\n[goojy]\nunrelated = yes")

    def test_write_on_the_right_default_config_file(self):
        self.write_config_file(whatever="spam")
        self.config_class.default_config_filenames.insert(0, "/non/existent")
        self.config.load([])
        self.config.whatever = "eggs"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = eggs\n")

    def test_write_empty_list_values_instead_of_double_quotes(self):
        """
        Since list values are strings, an empty string such as "" will be
        written to the config file as an option with a empty value instead of
        "".
        """
        self.write_config_file(spam="42")
        self.config.load([])
        self.config.spam = ""
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nspam = \n")

    def test_dont_write_config_specified_default_options(self):
        """
        Don't write options to the file if the value exactly matches the
        default and the value already existed in the original config file.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file()
        self.config.whatever = "spam"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]")

    def test_dont_write_unspecified_default_options(self):
        """
        Don't write options to the file if the value exactly matches the
        default and the value did not exist in the original config file.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file()
        self.config.whatever = "spam"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]")

    def test_dont_write_client_section_default_options(self):
        """
        Don't write options to the file if they exactly match the default and
        didn't already exist in the file.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file(whatever="eggs")
        self.config.whatever = "spam"
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]")

    def test_do_write_preexisting_default_options(self):
        """
        If the value of an option matches the default, but the option was
        already written in the file, then write it back to the file.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        config = "[my-config]\nwhatever = spam\n"
        config_filename = self.makeFile(config)
        self.config.load_configuration_file(config_filename)
        self.config.whatever = "spam"
        self.config.write()
        data = read_text_file(config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = spam\n")

    def test_dont_delete_explicitly_set_default_options(self):
        """
        If the user explicitly sets a configuration option to its default
        value, we shouldn't delete that option from the conf file when we
        write it, just to be nice.
        """
        self.reset_config(configuration_class=cfg_class(whatever="spam"))
        self.write_config_file(whatever="spam")
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]\nwhatever = spam")

    def test_dont_write_config_option(self):
        self.write_config_file()
        self.config.config = self.config_filename
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[my-config]")

    def test_write_command_line_options(self):
        self.reset_config(configuration_class=BabbleConfiguration)
        self.write_config_file()
        self.config.load(["--whatever", "spam"])
        self.config.write()
        data = read_text_file(self.config_filename)
        self.assertConfigEqual(data, "[babble]\nwhatever = spam\n")

    def test_comments_are_maintained(self):
        """
        When we write an updated config file, comments that existed previously
        are maintained.
        """
        config = "[my-config]\n# Comment 1\nwhatever = spam\n#Comment 2\n"
        filename = self.makeFile(config)
        self.config.load_configuration_file(filename)
        self.config.whatever = "eggs"
        self.config.write()
        new_config = read_text_file(filename)
        self.assertConfigEqual(
            new_config,
            "[my-config]\n# Comment 1\nwhatever = eggs\n#Comment 2\n")


class GetBindirTest(unittest.TestCase):

    BIN_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

    def test_config_has_valid_bindir(self):
        """get_bindir() returns the directory name found in the config."""
        cfg = BaseConfiguration()
        cfg.bindir = "/spam/eggs"
        bindir = get_bindir(cfg)

        self.assertEqual("/spam/eggs", bindir)

    def test_config_has_None_bindir(self):
        """get_bindir() """
        cfg = BaseConfiguration()
        cfg.bindir = None
        bindir = get_bindir(cfg)

        self.assertEqual(self.BIN_DIR, bindir)

    def test_config_has_no_bindir(self):
        """get_bindir() """
        cfg = object()
        bindir = get_bindir(cfg)

        self.assertEqual(self.BIN_DIR, bindir)

    def test_config_is_None(self):
        """get_bindir() """
        bindir = get_bindir(None)

        self.assertEqual(self.BIN_DIR, bindir)
