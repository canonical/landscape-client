from twisted.internet.defer import Deferred

from landscape.sysinfo.deployment import SysInfoConfiguration, ALL_PLUGINS, run
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


class RunTest(LandscapeTest):

    helpers = [StandardIOHelper]

    def test_registry_runs_plugin_and_gets_correct_information(self):
        run(["--sysinfo-plugins", "TestPlugin"], run_reactor=False)

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

        run(["--sysinfo-plugins", "TestPlugin"], run_reactor=False)

    def test_format_sysinfo_output_is_printed(self):
        format_sysinfo = self.mocker.replace("landscape.sysinfo.sysinfo."
                                             "format_sysinfo")
        format_sysinfo(ARGS, KWARGS)
        self.mocker.result("Hello there!")
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"], run_reactor=False)

        self.assertEquals(self.stdout.getvalue(), "Hello there!\n")

    def test_output_is_only_displayed_once_deferred_fires(self):
        deferred = Deferred()
        sysinfo = self.mocker.patch(SysInfoPluginRegistry)
        sysinfo.run()
        self.mocker.passthrough()
        self.mocker.result(deferred)
        self.mocker.replay()

        run(["--sysinfo-plugins", "TestPlugin"], run_reactor=False)

        self.assertNotIn("Test note", self.stdout.getvalue())
        deferred.callback(None)
        self.assertIn("Test note", self.stdout.getvalue())

    def test_default_arguments_load_default_plugins(self):
        result = run([], run_reactor=False)
        def check_result(result):
            self.assertIn("System load", self.stdout.getvalue())
            self.assertNotIn("Test note", self.stdout.getvalue())
        return result.addCallback(check_result)
