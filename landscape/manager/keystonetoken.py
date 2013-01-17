import os
import logging
from ConfigParser import ConfigParser, NoOptionError

from landscape.monitor.plugin import DataWatcher
from landscape.lib.persist import Persist


KEYSTONE_CONFIG_FILE = "/etc/keystone/keystone.conf"


# Yes, it should be just fine that we're using a MonitorPlugin
# (DataWatcher) from the landscape manager process.
class KeystoneToken(DataWatcher):
    """
    A plugin which pulls the admin_token from the keystone configuration file
    and sends it to the landscape server.
    """
    message_type = "keystone-token"
    message_key = "data"
    run_interval = 60 * 15

    def __init__(self, keystone_config_file=KEYSTONE_CONFIG_FILE):
        self._keystone_config_file = keystone_config_file

    def register(self, client):
        super(KeystoneToken, self).register(client)
        self._persist = Persist(
            filename=os.path.join(self.registry.config.data_path,
                "keystone.bpickle"))
        # radix XXX resynchronize is untested. does it even work in manager?
        self.registry.reactor.call_on("resynchronize", self._resynchronize)

    def _resynchronize(self):
        # radix XXX resynchronize is untested. does it even work in manager?
        self._persist.remove("data")

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
