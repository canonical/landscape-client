from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, RemoteBrokerHelper)
from landscape.manager.deployment import ManagerService, ManagerConfiguration
from landscape.manager.processkiller import ProcessKiller
from landscape.manager.scriptexecution import ALL_USERS
from landscape.broker.tests.test_remote import assertTransmitterActive
from landscape.tests.test_plugin import assertReceivesMessages


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = ManagerConfiguration()
        configuration.load(["--manager-plugins", "ProcessKiller",
                            "-d", self.make_path()])
        manager_service = ManagerService(configuration)
        plugins = manager_service.plugins
        self.assertEquals(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], ProcessKiller))

    def test_get_all_plugins(self):
        configuration = ManagerConfiguration()
        configuration.load(["--manager-plugins", "ALL",
                            "-d", self.make_path()])
        manager_service = ManagerService(configuration)
        self.assertEquals(len(manager_service.plugins), 3)

    def test_include_script_execution(self):
        configuration = ManagerConfiguration()
        configuration.load(["--include-manager-plugins", "ScriptExecution",
                            "-d", self.make_path()])
        manager_service = ManagerService(configuration)
        self.assertEquals(len(manager_service.plugins), 4)

    def test_get_allowed_script_users_with_users(self):
        """
        It's possible to specify a list of usernames to allow scripts to run
        as.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.make_path(),
                            "--script-users", "foo, bar,baz"])
        self.assertEquals(configuration.get_allowed_script_users(),
                          ["foo", "bar", "baz"])

    def test_get_allowed_script_users_all(self):
        """
        When script_users is "ALL", C{get_allowed_script_users} returns
        L{ALL_USERS}.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.make_path(),
                            "--script-users", "\tALL "])
        self.assertEquals(configuration.get_allowed_script_users(), ALL_USERS)

    def test_get_allowed_script_users_default(self):
        """
        If no script users are specified, the default is 'nobody'.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.make_path()])
        self.assertEquals(configuration.get_allowed_script_users(),
                          ["nobody"])



class DeploymentBusTests(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def test_dbus_reactor_transmitter_installed(self):
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.make_path(), "--bus", "session",
                            "--manager-plugins", "ProcessKiller"])
        manager_service = ManagerService(configuration)
        manager_service.startService()
        return assertTransmitterActive(self, self.broker_service,
                                       manager_service.reactor)

    def test_receives_messages(self):
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.make_path(), "--bus", "session",
                            "--manager-plugins", "ProcessKiller"])
        manager_service = ManagerService(configuration)
        manager_service.startService()
        return assertReceivesMessages(self, manager_service.dbus_service,
                                      self.broker_service, self.remote)
