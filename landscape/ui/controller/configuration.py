import logging

from landscape.ui.model.registration.proxy import RegistrationProxy
from landscape.ui.model.configuration.state import StateError


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
        if name in self.__dict__:
            return self.__dict__[name]
        else:
            return getattr(self._configuration, name)

    def __setattr__(self, name, value):
        # this test allows attributes to be set in the __init__ method
        if not '_initialised' in self.__dict__:
            return object.__setattr__(self, name, value)
        try:
            setattr(self._configuration, name, value)
        except AttributeError:
            return object.__setattr__(self, name, value)
        else:
            self._configuration.modify()

    def load(self):
        """
        Load the initial data from the configuration.
        """
        self._configuration.load_data()

    def revert(self):
        """
        Revert settings to those the configuration object originally found.
        """
        try:
            self._configuration.revert()
        except StateError:
            # We probably don't care.
            logging.info("landscape-client-settings-ui reverted with no "
                         "changes to revert.")

    def commit(self):
        """
        Persist settings via the configuration object.
        """
        try:
            self._configuration.persist()
        except StateError:
            # We probably don't care.
            logging.info("landscape-client-settings-ui committed with no "
                         "changes to commit.")

    def register(self, notify_method, error_method, succeed_method,
                 fail_method):
        """
        Perform registration using the L{RegistrationProxy}.
        """
        registration = RegistrationProxy(notify_method, error_method,
                                         succeed_method, fail_method)
        self.commit()
        self.stop = False

        if registration.challenge():
            registration.register(
                self._configuration.get_config_filename())
        else:
            fail_method("You do not have permission to connect the client.")
