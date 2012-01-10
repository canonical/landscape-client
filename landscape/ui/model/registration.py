import os

from landscape.configuration import (
    register, setup_http_proxy, check_account_name_and_password,
    check_script_users, register_ssl)
from landscape.sysvconfig import SysVConfig


class ObservableRegistration(object):

    def __init__(self):
        self._notification_observers = []
        self._error_observers = [] 
        self._succeed_observers = []
        self._fail_observers = []

    def notify_observers(self, message, end="\n", error=False):
        for fun in self._notification_observers:
            fun(message, error)

    def error_observers(self, error_list):
        for fun in self._error_observers:
            fun(error_list)

    def register_notification_observer(self, fun):
        self._notification_observers.append(fun)

    def register_error_observer(self, fun):
        self._error_observers.append(fun)

    def register_succeed_observer(self, fun):
        self._succeed_observers.append(fun)

    def register_fail_observer(self, fun):
        self._fail_observers.append(fun)

    def succeed(self):
        for fun in self._succeed_observers:
            fun()

    def fail(self):
        for fun in self._fail_observers:
            fun()
    
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
                            self.error_observers,
                            success_handler_f=self.succeed)
        else:
            self.error_observers([])


