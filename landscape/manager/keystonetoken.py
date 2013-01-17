import logging
from ConfigParser import ConfigParser, NoOptionError

from landscape.monitor.plugin import DataWatcher


KEYSTONE_CONFIG_FILE = "/etc/keystone/keystone.conf"


class KeystoneToken(DataWatcher):

    persist_name = "keystone-token"
    message_type = "keystone-token"
    message_key = "data"
    run_interval = 60 * 15

    def __init__(self, keystone_config_file=KEYSTONE_CONFIG_FILE):
        self._keystone_config_file = keystone_config_file

    def get_data(self):
        """
        Return the Keystone administrative token.
        """
        config = ConfigParser()
        config.read(self._keystone_config_file)
        try:
            admin_token = config.get("DEFAULT", "admin_token")
        except NoOptionError:
            logging.error("KeystoneToken: No admin_token found in %s"
                          % (self._keystone_config_file))
            return None
        return admin_token
