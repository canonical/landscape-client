import os

from landscape.configuration import (
    register, setup_http_proxy, check_account_name_and_password,
    check_script_users, register_ssl)
from landscape.sysvconfig import SysVConfig


class ObservableRegistration(object):

    def notify_observers(self, message, end="\n", error=False):
        pass

    def fail_observers(self, error_list):
        pass
    
    def setup(self, config):
        sysvconfig = SysVConfig()
        sysvconfig.set_start_on_boot(True)
        setup_http_proxy(config)
        check_account_name_and_password(config)
        check_script_users(config)
        register_ssl(config)
        config.write()
        try:
            sysvconfig.restart_landscape()
        except ProcessError:
            self.notify_observers("Couldn't restart the Landscape client.", 
                                  error=True)
            return False
        return True
        
    def register(self, config):
        config.silent = True
        config.no_start = False
        if self.setup(config):
            return register(config, self.notify_observers, 
                            self.fail_observers)
        else:
            self.fail_observers([])


