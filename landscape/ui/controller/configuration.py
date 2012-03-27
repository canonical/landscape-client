import logging

from gettext import gettext as _

from landscape.ui.constants import NOT_MANAGED, CANONICAL_MANAGED

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
        if name in ConfigController.__dict__:
            return object.__setattr__(self, name, value)
        else:
            try:
                setattr(self._configuration, name, value)
                self._configuration.modify()
            except AttributeError:
                return object.__setattr__(self, name, value)
            else:
                self._configuration.modify()

    def load(self):
        """
        Load the initial data from the configuration.
        """
        return self._configuration.load_data()

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

    def persist(self, on_notify, on_error, on_succeed, on_fail):
        """Persist settings via the configuration object."""
        try:
            self._configuration.persist()
        except StateError:
            # We probably don't care.
            logging.info("landscape-client-settings-ui committed with no "
                         "changes to commit.")
        if self._configuration.management_type == NOT_MANAGED:
            self.disable(on_notify, on_succeed, on_fail)
        else:
            self.register(on_notify, on_error, on_succeed, on_fail)

    def register(self, notify_method, error_method, succeed_method,
                 fail_method):
        """
        Perform registration using the L{RegistrationProxy}.
        """

        def registration_fail_wrapper():
            fail_method(action=_("Registering client failed"))

        def registration_succeed_wrapper():
            succeed_method(action=_("Registering client was successful"))

        registration = RegistrationProxy(
            on_register_notify=notify_method,
            on_register_error=error_method,
            on_register_succeed=registration_succeed_wrapper,
            on_register_fail=registration_fail_wrapper)
        if self._configuration.management_type == CANONICAL_MANAGED:
            notify_method(_("Attempting to register at %s") %
                          self._configuration.hosted_landscape_host)
        else:
            notify_method(_("Attempting to register at %s") %
                          self._configuration.local_landscape_host)
        registration.register(self._configuration.get_config_filename())
        registration.exit()

    def disable(self, notify_method, succeed_method, fail_method):
        """
        Disable landscape client via the L{RegistrationProxy}.
        """

        def disabling_fail_wrapper():
            fail_method(action=_("Disabling client failed"))

        def disabling_succeed_wrapper():
            succeed_method(action=_("Disabling client was successful"))

        registration = RegistrationProxy(
            on_disable_succeed=disabling_succeed_wrapper,
            on_disable_fail=disabling_fail_wrapper)
        notify_method(_("Attempting to disable landscape client."))
        registration.disable()
        registration.exit()
