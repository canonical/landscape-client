from logging.handlers import RotatingFileHandler
from logging import getLogger
import os
import unittest

import mock
from twisted.internet.defer import Deferred

from landscape.lib.fs import create_text_file
from landscape.lib.testing import (
        ConfigTestCase, TwistedTestCase, HelperTestCase, StandardIOHelper)

from landscape.sysinfo.deployment import (
    SysInfoConfiguration, ALL_PLUGINS, run, setup_logging,
    get_landscape_log_directory)
from landscape.sysinfo.testplugin import TestPlugin
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.load import Load
from landscape.sysinfo.landscapelink import LandscapeLink


class DeploymentTest(ConfigTestCase, unittest.TestCase):

    def setUp(self):
        super(DeploymentTest, self).setUp()

        class TestConfiguration(SysInfoConfiguration):
            default_config_filenames = [self.makeFile("")]

        self.configuration = TestConfiguration()

    def test_get_plugins(self):
        self.configuration.load(["--sysinfo-plugins", "Load,TestPlugin",
                                 "-d", self.makeDir()])
        plugins = self.configuration.get_plugins()
        self.assertEqual(len(plugins), 2)
        self.assertTrue(isinstance(plugins[0], Load))
        self.assertTrue(isinstance(plugins[1], TestPlugin))

    def test_get_all_plugins(self):
        self.configuration.load(["-d", self.makeFile()])
        plugins = self.configuration.get_plugins()
        self.assertEqual(len(plugins), len(ALL_PLUGINS))

    def test_landscape_link_not_default(self):
        self.configuration.load(["-d", self.makeFile()])
        plugins = self.configuration.get_plugins()
        for plugin in plugins:
            self.assertFalse(isinstance(plugin, LandscapeLink))

    def test_exclude_plugins(self):
        exclude = ",".join(x for x in ALL_PLUGINS if x != "Load")
        self.configuration.load(["--exclude-sysinfo-plugins", exclude,
                                 "-d", self.makeDir()])
        plugins = self.configuration.get_plugins()
        self.assertEqual(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], Load))

    def test_config_file(self):
        filename = self.makeFile()
        create_text_file(filename, "[sysinfo]\nsysinfo_plugins = TestPlugin\n")
        self.configuration.load(["--config", filename, "-d", self.makeDir()])
        plugins = self.configuration.get_plugins()
        self.assertEqual(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], TestPlugin))


class FakeReactor(object):
    """
    Something that's simpler and more reusable than a bunch of mocked objects.
    """

    def __init__(self):
        self.queued_calls = []
        self.scheduled_calls = []
        self.running = False

    def callWhenRunning(self, callable):
        self.queued_calls.append(callable)

    def run(self):
        self.running = True

    def callLater(self, seconds, callable, *args, **kwargs):
        self.scheduled_calls.append((seconds, callable, args, kwargs))

    def stop(self):
        self.running = False


class RunTest(HelperTestCase, ConfigTestCase, TwistedTestCase,
              unittest.TestCase):

    helpers = [StandardIOHelper]

    def setUp(self):
        super(RunTest, self).setUp()
        self._old_filenames = SysInfoConfiguration.default_config_filenames
        SysInfoConfiguration.default_config_filenames = [self.makeFile("")]

    def tearDown(self):
        super(RunTest, self).tearDown()
        SysInfoConfiguration.default_config_filenames = self._old_filenames
        logger = getLogger("landscape-sysinfo")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    def test_registry_runs_plugin_and_gets_correct_information(self):
        run(["--sysinfo-plugins", "TestPlugin"])

        from landscape.sysinfo.testplugin import current_instance

        self.assertEqual(current_instance.has_run, True)
        sysinfo = current_instance.sysinfo
        self.assertEqual(sysinfo.get_headers(),
                         [("Test header", "Test value")])
        self.assertEqual(sysinfo.get_notes(), ["Test note"])
        self.assertEqual(sysinfo.get_footnotes(), ["Test footnote"])

    @mock.patch("landscape.sysinfo.deployment.format_sysinfo")
    def test_format_sysinfo_gets_correct_information(self, format_sysinfo):
        run(["--sysinfo-plugins", "TestPlugin"])
        format_sysinfo.assert_called_once_with(
            [("Test header", "Test value")],
            ["Test note"], ["Test footnote"],
            indent="  ")

    def test_format_sysinfo_output_is_printed(self):
        with mock.patch(
                "landscape.sysinfo.deployment.format_sysinfo",
                return_value="Hello there!") as format_sysinfo:
            run(["--sysinfo-plugins", "TestPlugin"])

        self.assertTrue(format_sysinfo.called)
        self.assertEqual(self.stdout.getvalue(), "Hello there!\n")

    def test_output_is_only_displayed_once_deferred_fires(self):
        deferred = Deferred()

        # We mock the sysinfo.run() to return a Deferred but still
        # run the actual sysinfo.run() to gather the results from all
        # the plugins.  We cannot easily combine return_value and
        # side_effect because side_effect operates on the return_value,
        # thus firing the callback and writing sysinfo out to stdout.
        sysinfo = SysInfoPluginRegistry()
        original_sysinfo_run = sysinfo.run

        def wrapped_sysinfo_run(*args, **kwargs):
            original_sysinfo_run(*args, **kwargs)
            return deferred
        sysinfo.run = mock.Mock(side_effect=wrapped_sysinfo_run)

        run(["--sysinfo-plugins", "TestPlugin"], sysinfo=sysinfo)

        sysinfo.run.assert_called_once_with()

        self.assertNotIn("Test note", self.stdout.getvalue())
        deferred.callback(None)
        self.assertIn("Test note", self.stdout.getvalue())

    def test_default_arguments_load_default_plugins(self):
        result = run([])

        def check_result(result):
            self.assertIn("System load", self.stdout.getvalue())
            self.assertNotIn("Test note", self.stdout.getvalue())

        return result.addCallback(check_result)

    def test_missing_config_file(self):
        """The process doesn't fail if there is no config file."""
        # Existing revert in tearDown will handle undoing this
        SysInfoConfiguration.default_config_filenames = []
        result = run([])

        def check_result(result):
            self.assertIn("System load", self.stdout.getvalue())

        return result.addCallback(check_result)

    def test_plugins_called_after_reactor_starts(self):
        """
        Plugins are invoked after the reactor has started, so that they can
        spawn processes without concern for race conditions.
        """
        reactor = FakeReactor()
        d = run(["--sysinfo-plugins", "TestPlugin"], reactor=reactor)
        self.assertEqual(self.stdout.getvalue(), "")

        self.assertTrue(reactor.running)
        for x in reactor.queued_calls:
            x()

        self.assertEqual(
            self.stdout.getvalue(),
            "  Test header: Test value\n\n  => Test note\n\n  Test footnote\n")
        return d

    def test_stop_scheduled_in_callback(self):
        """
        Because of tm:3011, reactor.stop() must be called in a scheduled call.
        """
        reactor = FakeReactor()
        d = run(["--sysinfo-plugins", "TestPlugin"], reactor=reactor)
        for x in reactor.queued_calls:
            x()
        self.assertEqual(reactor.scheduled_calls, [(0, reactor.stop, (), {})])
        return d

    def test_stop_reactor_even_when_sync_exception_from_sysinfo_run(self):
        """
        Even when there's a synchronous exception from run_sysinfo, the reactor
        should be stopped.
        """
        self.log_helper.ignore_errors(ZeroDivisionError)
        reactor = FakeReactor()
        sysinfo = SysInfoPluginRegistry()
        sysinfo.run = lambda: 1 / 0
        d = run(["--sysinfo-plugins", "TestPlugin"], reactor=reactor,
                sysinfo=sysinfo)

        for x in reactor.queued_calls:
            x()

        self.assertEqual(reactor.scheduled_calls, [(0, reactor.stop, (), {})])
        return self.assertFailure(d, ZeroDivisionError)

    def test_get_landscape_log_directory_unprivileged(self):
        """
        If landscape-sysinfo is running as a non-privileged user the
        log directory is stored in their home directory.
        """
        self.assertEqual(get_landscape_log_directory(),
                         os.path.expanduser("~/.landscape"))

    def test_get_landscape_log_directory_privileged(self):
        """
        If landscape-sysinfo is running as a privileged user, then the logs
        should be stored in the system-wide log directory.
        """
        with mock.patch("os.getuid", return_value=0) as uid_mock:
            self.assertEqual(
                get_landscape_log_directory(), "/var/log/landscape")
            uid_mock.assert_called_once_with()

    def test_wb_logging_setup(self):
        """
        setup_logging sets up a "landscape-sysinfo" logger which rotates every
        week and does not propagate logs to higher-level handlers.
        """
        # This hecka whiteboxes but there aren't any underscores!
        logger = getLogger("landscape-sysinfo")
        self.assertEqual(logger.handlers, [])
        setup_logging(landscape_dir=self.makeDir())
        logger = getLogger("landscape-sysinfo")
        self.assertEqual(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertTrue(isinstance(handler, RotatingFileHandler))
        self.assertEqual(handler.maxBytes, 500 * 1024)
        self.assertEqual(handler.backupCount, 1)
        self.assertFalse(logger.propagate)

    def test_setup_logging_logs_to_var_log_if_run_as_root(self):
        with mock.patch.object(os, "getuid", return_value=0) as mock_getuid, \
                mock.patch.object(
                    os.path, "isdir", return_value=False) as mock_isdir, \
                mock.patch.object(os, "mkdir") as mock_mkdir, \
                mock.patch("logging.open", create=True) as mock_open:
            logger = getLogger("landscape-sysinfo")
            self.assertEqual(logger.handlers, [])

            setup_logging()

        mock_getuid.assert_called_with()
        mock_isdir.assert_called_with("/var/log/landscape")
        mock_mkdir.assert_called_with("/var/log/landscape")
        self.assertEqual(
            mock_open.call_args_list[0][0],
            ("/var/log/landscape/sysinfo.log", "a")
        )
        handler = logger.handlers[0]
        self.assertTrue(isinstance(handler, RotatingFileHandler))
        self.assertEqual(handler.baseFilename,
                         "/var/log/landscape/sysinfo.log")

    def test_create_log_dir(self):
        log_dir = self.makeFile()
        self.assertFalse(os.path.exists(log_dir))
        setup_logging(landscape_dir=log_dir)
        self.assertTrue(os.path.exists(log_dir))

    def test_run_sets_up_logging(self):
        with mock.patch(
                "landscape.sysinfo.deployment"
                ".setup_logging") as setup_logging_mock:
            run(["--sysinfo-plugins", "TestPlugin"])
        setup_logging_mock.assert_called_once_with()

    def test_run_setup_logging_exits_gracefully(self):
        io_error = IOError("Read-only filesystem.")
        with mock.patch(
                "landscape.sysinfo.deployment.setup_logging",
                side_effect=io_error):
            error = self.assertRaises(
                SystemExit, run, ["--sysinfo-plugins", "TestPlugin"])
        self.assertEqual(
            error.code, "Unable to setup logging. Read-only filesystem.")
