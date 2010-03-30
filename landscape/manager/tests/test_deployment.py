import os

from twisted.internet.defer import Deferred

from landscape.tests.helpers import (
    LandscapeTest, LandscapeIsolatedTest, RemoteBrokerHelper)
from landscape.manager.deployment import ManagerService, ManagerConfiguration
from landscape.manager.processkiller import ProcessKiller
from landscape.manager.scriptexecution import ALL_USERS
from landscape.manager.eucalyptus import Eucalyptus
from landscape.manager.store import ManagerStore
from landscape.broker.tests.test_remote import assertTransmitterActive
from landscape.tests.test_plugin import assertReceivesMessages


class DeploymentTest(LandscapeTest):

    def test_get_plugins(self):
        configuration = ManagerConfiguration()
        configuration.load(["--manager-plugins", "ProcessKiller",
                            "-d", self.makeDir()])
        manager_service = ManagerService(configuration)
        plugins = manager_service.plugins
        self.assertEquals(len(plugins), 1)
        self.assertTrue(isinstance(plugins[0], ProcessKiller))

    def test_get_all_plugins(self):
        configuration = ManagerConfiguration()
        configuration.load(["--manager-plugins", "ALL",
                            "-d", self.makeDir()])
        manager_service = ManagerService(configuration)
        self.assertEquals(len(manager_service.plugins), 4)

    def test_include_script_execution(self):
        configuration = ManagerConfiguration()
        configuration.load(["--include-manager-plugins", "ScriptExecution"])
        manager_service = ManagerService(configuration)
        self.assertEquals(len(manager_service.plugins), 5)

    def test_include_eucalyptus(self):
        """
        The L{Eucalyptus} plugin can be loaded via command line configuration.
        """
        configuration = ManagerConfiguration()
        configuration.load(["--include-manager-plugins", "Eucalyptus"])
        manager_service = ManagerService(configuration)
        self.assertEquals(len(manager_service.plugins), 5)
        plugin = filter(lambda plugin: isinstance(plugin, Eucalyptus),
                        manager_service.plugins)
        self.assertTrue(plugin)

    def test_get_allowed_script_users_with_users(self):
        """
        It's possible to specify a list of usernames to allow scripts to run
        as.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.makeDir(),
                            "--script-users", "foo, bar,baz"])
        self.assertEquals(configuration.get_allowed_script_users(),
                          ["foo", "bar", "baz"])

    def test_get_allowed_script_users_all(self):
        """
        When script_users is "ALL", C{get_allowed_script_users} returns
        L{ALL_USERS}.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.makeDir(),
                            "--script-users", "\tALL "])
        self.assertEquals(configuration.get_allowed_script_users(), ALL_USERS)

    def test_get_allowed_script_users_default(self):
        """
        If no script users are specified, the default is 'nobody'.
        """
        configuration = ManagerConfiguration()
        configuration.load(["-d", self.makeDir()])
        self.assertEquals(configuration.get_allowed_script_users(),
                          ["nobody"])


class DeploymentBusTests(LandscapeIsolatedTest):

    helpers = [RemoteBrokerHelper]

    def setUp(self):
        super(DeploymentBusTests, self).setUp()
        configuration = ManagerConfiguration()
        self.path = self.makeDir()
        configuration.load(["-d", self.path, "--bus", "session",
                            "--manager-plugins", "ProcessKiller"])
        self.manager_service = ManagerService(configuration)
        self.manager_service.startService()

    def test_dbus_reactor_transmitter_installed(self):
        return assertTransmitterActive(self, self.broker_service,
                                       self.manager_service.reactor)

    def test_receives_messages(self):
        return assertReceivesMessages(self, self.manager_service.dbus_service,
                                      self.broker_service, self.remote)

    def test_manager_store(self):
        self.assertNotIdentical(self.manager_service.registry.store, None)
        self.assertTrue(
            isinstance(self.manager_service.registry.store, ManagerStore))
        self.assertTrue(
            os.path.isfile(os.path.join(self.path, "manager.database")))

    def test_register_plugin_on_broker_started(self):
        """
        When the broker is restarted, it fires a "broker-started" signal which
        makes the Manager plugin register itself again.
        """
        d = Deferred()
        def register_plugin(bus_name, object_path):
            d.callback((bus_name, object_path))
        def patch(ignore):
            self.manager_service.remote_broker.register_plugin = register_plugin
            self.broker_service.dbus_object.broker_started()
            return d
        return self.remote.get_registered_plugins(
            ).addCallback(patch
            ).addCallback(self.assertEquals,
                ("com.canonical.landscape.Manager",
                 "/com/canonical/landscape/Manager"))

    def test_register_message_on_broker_started(self):
        """
        When the broker is restarted, it fires a "broker-started" signal which
        makes the Manager plugin register all registered messages again.
        """
        self.manager_service.registry.register_message("foo", lambda x: None)
        d = Deferred()
        def register_client_accepted_message_type(type):
            if type == "foo":
                d.callback(type)
        def patch(ignore):
            self.manager_service.remote_broker.register_client_accepted_message_type = \
                register_client_accepted_message_type
            self.broker_service.dbus_object.broker_started()
            return d
        return self.remote.get_registered_plugins(
            ).addCallback(patch
            ).addCallback(self.assertEquals, "foo")
