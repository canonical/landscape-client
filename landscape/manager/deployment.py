import os

from twisted.python.reflect import namedClass

from landscape.deployment import (LandscapeService, Configuration,
                                  run_landscape_service)
from landscape.broker.remote import (RemoteBroker,
                                     DBusSignalToReactorTransmitter)
from landscape.manager.manager import ManagerPluginRegistry, ManagerDBusObject


ALL_PLUGINS = ["ProcessKiller", "PackageManager", "UserManager",
               "ShutdownManager", "ReleaseUpgrade"]


class ManagerConfiguration(Configuration):
    """Specialized configuration for the Landscape Manager."""

    def make_parser(self):
        """
        Specialize L{Configuration.make_parser}, adding many
        manager-specific options.
        """
        parser = super(ManagerConfiguration, self).make_parser()

        parser.add_option("--manager-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of manager plugins to "
                               "use. ALL means use all plugins.",
                          default="ALL")
        parser.add_option("--include-manager-plugins", metavar="PLUGIN_LIST",
                          help="Comma-delimited list of manager plugins to "
                               "enable, in addition to the defaults.")
        parser.add_option("--script-users", metavar="USERS",
                          help="Comma-delimited list of usernames that scripts "
                               "may be run as. Default is to allow all users.")
        return parser

    @property
    def plugin_factories(self):
        plugin_names = []
        if self.manager_plugins == "ALL":
            plugin_names = ALL_PLUGINS
        elif self.manager_plugins:
            plugin_names = self.manager_plugins.split(",")
        if self.include_manager_plugins:
            plugin_names += self.include_manager_plugins.split(",")
        return [x.strip() for x in plugin_names]

    def get_allowed_script_users(self):
        """
        Based on the C{script_users} configuration value, return the users that
        should be allowed to run scripts.

        If the value is "ALL", then
        L{landscape.manager.scriptexecution.ALL_USERS} will be returned.  If
        there is no specified value, then C{nobody} will be allowed.
        """
        if not self.script_users:
            return ["nobody"]
        if self.script_users.strip() == "ALL":
            from landscape.manager.scriptexecution import ALL_USERS
            return ALL_USERS
        return [x.strip() for x in self.script_users.split(",")]


class ManagerService(LandscapeService):

    service_name = "manager"

    def __init__(self, config):
        super(ManagerService, self).__init__(config)
        self.plugins = self.get_plugins()

    def get_plugins(self):
        return [namedClass("landscape.manager.%s.%s"
                           % (plugin_name.lower(), plugin_name))()
                for plugin_name in self.config.plugin_factories]

    def startService(self):
        super(ManagerService, self).startService()
        self.remote_broker = RemoteBroker(self.bus)
        store_name = os.path.join(self.config.data_path, "manager.database")
        self.registry = ManagerPluginRegistry(self.remote_broker, self.reactor,
                                              self.config, self.bus, store_name)
        self.dbus_service = ManagerDBusObject(self.bus, self.registry)
        DBusSignalToReactorTransmitter(self.bus, self.reactor)

        for plugin in self.plugins:
            self.registry.add(plugin)

        def broker_started():
            self.remote_broker.register_plugin(self.dbus_service.bus_name,
                                               self.dbus_service.object_path)
            self.registry.broker_started()

        broker_started()
        self.bus.add_signal_receiver(broker_started, "broker_started")


def run(args):
    run_landscape_service(ManagerConfiguration, ManagerService, args,
                          ManagerDBusObject.bus_name)
