import os

from logging.handlers import RotatingFileHandler
from logging import getLogger

from twisted.internet.defer import Deferred

from landscape.sysinfo.deployment import (
    SysInfoConfiguration, ALL_PLUGINS, run, setup_logging)
from landscape.sysinfo.testplugin import TestPlugin
from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.load import Load

from landscape.tests.helpers import LandscapeTest, StandardIOHelper
from landscape.tests.mocker import ARGS, KWARGS


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "Load,TestPlugin",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), 2)
        self.assertTrue(isinstance(plugins[0], Load))
        self.assertTrue(isinstance(plugins[1], TestPlugin))

    def test_get_all_plugins(self):
        configuration = SysInfoConfiguration()
        configuration.load(["--sysinfo-plugins", "ALL",
                            "-d", self.make_path()])
        plugins = configuration.get_plugins()
        self.assertEquals(len(plugins), len(ALL_PLUGINS))


class FakeReactor(object):
    """
    Something that's easier to understand and more reusable than a bunch of
    mocker
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


class RunTest(LandscapeTest):

    helpers = [StandardIOHelper]

    def tearDown(self):
        super(RunTest, self).tearDown()
        logger = getLogger("landscape-sysinfo")
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)

    def test_registry_runs_plugin_and_gets_correct_information(self):
        run(["--sysinfo-plugins", "TestPlugin"])

        from landscape.sysinfo.testplugin import current_instance

        self.assertEquals(current_instance.has_run, True)
        sysinfo = current_instance.sysinfo
        self.assertEquals(sysinfo.get_headers(),
                          [("Test header", "Test value")])
        self.assertEquals(sysinfo.get_notes(), ["Test note"])
        self.assertEquals(sysinfo.get_footnotes(), ["Test footnote"])

    def test_format_sysinfo_gets_correct_information(self):
        format_sysinfo = self.mocker.replace("landscape.sysinfo.sysinfo."
                                             "format_sysinfo")
        format_sysinfo([("Test header", "Test value")],
                       ["Test note"], ["Test footnote"],
                       indent="  ")
        format_sysinfo(ARGS, KWARGS)
        self.mocker.count(0)
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"])

    def test_format_sysinfo_output_is_printed(self):
        format_sysinfo = self.mocker.replace("landscape.sysinfo.sysinfo."
                                             "format_sysinfo")
        format_sysinfo(ARGS, KWARGS)
        self.mocker.result("Hello there!")
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"])

        self.assertEquals(self.stdout.getvalue(), "Hello there!\n")

    def test_output_is_only_displayed_once_deferred_fires(self):
        deferred = Deferred()
        sysinfo = self.mocker.patch(SysInfoPluginRegistry)
        sysinfo.run()
        self.mocker.passthrough()
        self.mocker.result(deferred)
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"])

        self.assertNotIn("Test note", self.stdout.getvalue())
        deferred.callback(None)
        self.assertIn("Test note", self.stdout.getvalue())

    def test_default_arguments_load_default_plugins(self):
        result = run([])
        def check_result(result):
            self.assertIn("System load", self.stdout.getvalue())
            self.assertNotIn("Test note", self.stdout.getvalue())
        return result.addCallback(check_result)

    def test_plugins_called_after_reactor_starts(self):
        """
        Plugins are invoked after the reactor has started, so that they can
        spawn processes without concern for race conditions.
        """
        reactor = FakeReactor()
        d = run(["--sysinfo-plugins", "TestPlugin"], reactor=reactor)
        self.assertEquals(self.stdout.getvalue(), "")

        self.assertTrue(reactor.running)
        for x in reactor.queued_calls:
            x()

        self.assertEquals(
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
        self.assertEquals(reactor.scheduled_calls, [(0, reactor.stop, (), {})])
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

        self.assertEquals(reactor.scheduled_calls, [(0, reactor.stop, (), {})])
        return self.assertFailure(d, ZeroDivisionError)

    def test_wb_logging_setup(self):
        """
        setup_logging sets up a "landscape-sysinfo" logger which rotates every
        week and does not propagate logs to higher-level handlers.
        """
        # This hecka whiteboxes but there aren't any underscores!
        logger = getLogger("landscape-sysinfo")
        self.assertEquals(logger.handlers, [])
        setup_logging()
        logger = getLogger("landscape-sysinfo")
        self.assertEquals(len(logger.handlers), 1)
        handler = logger.handlers[0]
        self.assertTrue(isinstance(handler, RotatingFileHandler))
        self.assertEquals(handler.maxBytes, 500*1024)
        self.assertEquals(handler.backupCount, 1)
        self.assertFalse(logger.propagate)

    def test_create_log_dir(self):
        log_dir = self.make_path()
        self.assertFalse(os.path.exists(log_dir))
        setup_logging(landscape_dir=log_dir)
        self.assertTrue(os.path.exists(log_dir))
        

    def test_run_sets_up_logging(self):
        setup_logging_mock = self.mocker.replace(
            "landscape.sysinfo.deployment.setup_logging")
        setup_logging_mock()
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"])
