import socket
from landscape.ui.model.registration.proxy import RegistrationProxy
from landscape.ui.model.configuration.state import (
    derive_url_from_host_name, derive_ping_url_from_host_name,
    derive_server_host_name_from_url, ModifiedState, StateError)


class ConfigControllerLockError(Exception):
    pass


class ConfigController(object):
    """
    L{ConfigContoller} defines actions to take against a configuration object,
    providing starting values from the file, allowing them to be changed
    transiently, reverted or committed.
    """

    DEFAULT_DEDICATED_ACCOUNT_NAME = "standalone"

    def __init__(self, configuration):
        self._observers = []
        self._configuration = configuration
        self._initialised = True

    def __getattr__(self, name):
        if self.__dict__.has_key(name):
            return self.__dict__[name]
        else:
            return getattr(self._configuration, name)

    def __setattr__(self, name, value):
        # this test allows attributes to be set in the __init__ method
        if not self.__dict__.has_key('_initialised'):
            return object.__setattr__(self, name, value)
        try:
            setattr(self._configuration, name, value)
            self._configuration.modify()
        except AttributeError:
            return object.__setattr__(self, name, value)

    def register_observer(self, function):
        "Register functions that observer modify/unmodify."
        self._observers.append(function)

    def notify_observers(self, modified):
        "Notify observers of modification events.  L{Modified} is boolean."
        for function in self._observers:
            function(modified)

    def load(self):
        "Load the initial data from the configuration"
        self._configuration.load_data()

    def revert(self):
        "Revert settings to those the configuration object originally found."
        try:
            self._configuration.revert()
        except StateError:
            # We probably don't care.
            pass

    def commit(self):
        "Persist settings via the configuration object."
        self._configuration.persist()

    def register(self, on_notify, on_error, on_success, on_failure, on_idle):
        "Invoke model level registration without completely locking the view."

        def succeed_handler(result):
            succeed, message = result
            if succeed:
                on_success(message)
            else:
                on_failure(message)

        def failure_handler(result):
            on_failure(result)

        registration = RegistrationProxy(on_notify, on_error,
                                         on_success, on_failure)
        self.commit()
        self.stop = False

        if registration.challenge():
            registration.register(
                self._configuration.get_config_filename(),
                reply_handler=succeed_handler,
                error_handler=failure_handler)
        else:
            on_failure(
                "Sorry, you do not have permission to connect the client.")
