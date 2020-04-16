import os

from landscape.client.deployment import Configuration
from landscape.client.manager.scriptexecution import ALL_USERS


ALL_PLUGINS = ["ProcessKiller", "PackageManager", "UserManager",
               "ShutdownManager", "AptSources", "HardwareInfo",
               "KeystoneToken"]


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
                          help="Comma-delimited list of usernames that scripts"
                               " may be run as. Default is to allow all "
                               "users.")
        parser.add_option("--script-output-limit",
                          metavar="SCRIPT_OUTPUT_LIMIT",
                          type="int", default=512,
                          help="Maximum allowed output size that scripts"
                               " can send. "
                               "Script output will be truncated at that limit."
                               " Default is 512 (kB)")

        return parser

    @property
    def plugin_factories(self):
        plugin_names = []
        if self.manager_plugins == "ALL":
            plugin_names = ALL_PLUGINS[:]
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
            return ALL_USERS
        return [x.strip() for x in self.script_users.split(",")]

    @property
    def store_filename(self):
        return os.path.join(self.data_path, "manager.database")
