import os
import logging
from ConfigParser import ConfigParser, NoOptionError

from landscape.monitor.plugin import DataWatcher
from landscape.lib.persist import Persist


KEYSTONE_CONFIG_FILE = "/etc/keystone/keystone.conf"


class KeystoneToken(DataWatcher):
    """
    A plugin which pulls the admin_token from the keystone configuration file
    and sends it to the landscape server.
    """
    message_type = "keystone-token"
    message_key = "data"
    run_interval = 60 * 15
    scope = "openstack"

    def __init__(self, keystone_config_file=KEYSTONE_CONFIG_FILE):
        self._keystone_config_file = keystone_config_file

    def register(self, client):
        super(KeystoneToken, self).register(client)
        self._persist_filename = os.path.join(self.registry.config.data_path,
                                              "keystone.bpickle")
        self._persist = Persist(filename=self._persist_filename)
        self.registry.reactor.call_every(self.registry.config.flush_interval,
                                         self.flush)

    def _reset(self):
        """
        Reset the persist.
        """
        self._persist.remove("data")

    def flush(self):
        self._persist.save(self._persist_filename)

    def get_data(self):
        """
        Return the Keystone administrative token.
        """
        if not os.path.exists(self._keystone_config_file):
            return None

        config = ConfigParser()
        config.read(self._keystone_config_file)
        try:
            admin_token = config.get("DEFAULT", "admin_token")
        except NoOptionError:
            logging.error("KeystoneToken: No admin_token found in %s"
                          % (self._keystone_config_file))
            return None
        return admin_token
