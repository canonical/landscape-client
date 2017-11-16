from landscape.client.tests.helpers import LandscapeTest
from landscape.client.manager.config import ManagerConfiguration, ALL_PLUGINS
from landscape.client.manager.scriptexecution import ALL_USERS


class ManagerConfigurationTest(LandscapeTest):

    def setUp(self):
        super(ManagerConfigurationTest, self).setUp()
        self.config = ManagerConfiguration()

    def test_plugin_factories(self):
        """By default all plugins are enabled."""
        self.assertEqual(["ProcessKiller", "PackageManager", "UserManager",
                          "ShutdownManager", "AptSources", "HardwareInfo",
                          "KeystoneToken"],
                         ALL_PLUGINS)
        self.assertEqual(ALL_PLUGINS, self.config.plugin_factories)

    def test_plugin_factories_with_manager_plugins(self):
        """
        The C{--manager-plugins} command line option can be used to specify
        which plugins should be active.
        """
        self.config.load(["--manager-plugins", "ProcessKiller"])
        self.assertEqual(self.config.plugin_factories, ["ProcessKiller"])

    def test_include_script_execution(self):
        """
        Extra plugins can be specified with the C{--include-manager-plugins}
        command line option.
        """
        self.config.load(["--include-manager-plugins", "ScriptExecution"])
        self.assertEqual(len(self.config.plugin_factories),
                         len(ALL_PLUGINS) + 1)
        self.assertTrue('ScriptExecution' in self.config.plugin_factories)

    def test_get_allowed_script_users(self):
        """
        If no script users are specified, the default is 'nobody'.
        """
        self.assertEqual(self.config.get_allowed_script_users(), ["nobody"])

    def test_get_allowed_script_users_all(self):
        """
        When script_users is C{ALL}, C{get_allowed_script_users} returns
        L{ALL_USERS}.
        """
        self.config.load(["--script-users", "\tALL "])
        self.assertIs(self.config.get_allowed_script_users(), ALL_USERS)

    def test_get_allowed_script_users_with_users(self):
        """
        It's possible to specify a list of usernames to allow scripts to run
        as.
        """
        self.config.load(["--script-users", "foo, bar,baz"])
        self.assertEqual(self.config.get_allowed_script_users(),
                         ["foo", "bar", "baz"])
