import copy

from landscape.lib.network import get_fqdn

from landscape.ui.constants import CANONICAL_MANAGED, NOT_MANAGED
from landscape.ui.model.configuration.proxy import ConfigurationProxy


HOSTED_LANDSCAPE_HOST = "landscape.canonical.com"
LOCAL_LANDSCAPE_HOST = ""

HOSTED_ACCOUNT_NAME = ""
LOCAL_ACCOUNT_NAME = "standalone"

HOSTED_PASSWORD = ""
LOCAL_PASSWORD = ""

HOSTED = "hosted"
LOCAL = "local"
MANAGEMENT_TYPE = "management-type"
COMPUTER_TITLE = "computer-title"
LANDSCAPE_HOST = "landscape-host"
ACCOUNT_NAME = "account-name"
PASSWORD = "password"


DEFAULT_DATA = {
    MANAGEMENT_TYPE: NOT_MANAGED,
    COMPUTER_TITLE: get_fqdn(),
    HOSTED: {
        LANDSCAPE_HOST: HOSTED_LANDSCAPE_HOST,
        ACCOUNT_NAME: HOSTED_ACCOUNT_NAME,
        PASSWORD: HOSTED_PASSWORD},
    LOCAL: {
        LANDSCAPE_HOST: LOCAL_LANDSCAPE_HOST,
        ACCOUNT_NAME: LOCAL_ACCOUNT_NAME,
        PASSWORD: LOCAL_PASSWORD}}


def derive_server_host_name_from_url(url):
    """
    Extract the hostname part from a URL.
    """
    try:
        without_protocol = url[url.index("://") + 3:]
    except ValueError:
        without_protocol = url
    try:
        return without_protocol[:without_protocol.index("/")]
    except ValueError:
        return without_protocol


def derive_url_from_host_name(host_name):
    """
    Extrapolate a url from a host name.
    """
    #Reuse this code to make sure it's a proper host name
    host_name = derive_server_host_name_from_url(host_name)
    return "https://" + host_name + "/message-system"


def derive_ping_url_from_host_name(host_name):
    """
    Extrapolate a ping_url from a host name.
    """
    #Reuse this code to make sure it's a proper host name
    host_name = derive_server_host_name_from_url(host_name)
    return "http://" + host_name + "/ping"


class StateError(Exception):
    """
    An exception that is raised when there is an error relating to the current
    state.
    """


class TransitionError(Exception):
    """
    An L{Exception} that is raised when a valid transition between states fails
    for some non state related reason.  For example, this error is raised when
    the user does not have the privilege of reading the configuration file,
    this causes the transition from L{VirginState} to L{InitialisedState} to
    fail but not because that transition from one state to another was not
    permitted, but rather the transition encountered an error.
    """


class ConfigurationState(object):
    """
    Base class for states used in the L{ConfigurationModel}.
    """
    def __init__(self, data, proxy, uisettings):
        self._data = copy.deepcopy(data)
        self._proxy = proxy
        self._uisettings = uisettings

    def get_config_filename(self):
        return self._proxy.get_config_filename()

    def get(self, *args):
        """
        Retrieve only valid values from two level dictionary based tree.

        This mainly served to pick up programming errors and could easily be
        replaced with a simpler scheme.
        """
        arglen = len(args)
        if arglen > 2 or arglen == 0:
            raise TypeError(
                "get() takes either 1 or 2 keys (%d given)" % arglen)
        if arglen == 2:  # We're looking for a leaf on a branch
            sub_dict = None
            if args[0] in [HOSTED, LOCAL]:
                sub_dict = self._data.get(args[0], {})
            sub_dict = self._data[args[0]]
            if not isinstance(sub_dict, dict):
                raise KeyError(
                    "Compound key [%s][%s] is invalid. The data type " +
                    "returned from the first index was %s." %
                    sub_dict.__class__.__name__)
            return sub_dict.get(args[1], None)
        else:
            if args[0] in (MANAGEMENT_TYPE, COMPUTER_TITLE):
                return self._data.get(args[0], None)
            else:
                raise KeyError("Key [%s] is invalid. " % args[0])

    def set(self, *args):
        """
        Set only valid values from two level dictionary based tree.

        This mainly served to pick up programming errors and could easily be
        replaced with a simpler scheme.
        """
        arglen = len(args)
        if arglen < 2 or arglen > 3:
            raise TypeError("set() takes either 1 or 2 keys and exactly 1 " +
                            "value (%d arguments given)" % arglen)
        if arglen == 2:  # We're setting a leaf attached to the root
            self._data[args[0]] = args[1]
        else:  # We're setting a leaf on a branch
            sub_dict = None
            if args[0] in [HOSTED, LOCAL]:
                sub_dict = self._data.get(args[0], {})
            if not isinstance(sub_dict, dict):
                raise KeyError("Compound key [%s][%s] is invalid. The data " +
                               "type returned from the first index was %s."
                               % sub_dict.__class__.__name__)
            sub_dict[args[1]] = args[2]
            self._data[args[0]] = sub_dict

    def load_data(self, asynchronous=True, exit_method=None):
        raise NotImplementedError

    def modify(self):
        raise NotImplementedError

    def revert(self):
        raise NotImplementedError

    def persist(self):
        raise NotImplementedError

    def exit(self, asynchronous=True, exit_method=None):
        return ExitedState(self._data, self._proxy, self._uisettings,
                           asynchronous=asynchronous, exit_method=exit_method)


class Helper(object):
    """
    Base class for all state transition helpers.

    It is assumed that the Helper classes are "friends" of the
    L{ConfigurationState} classes and can have some knowledge of their
    internals.  They shouldn't be visible to users of the
    L{ConfigurationState}s and in general we should avoid seeing the
    L{ConfigurationState}'s _data attribute outside this module.
    """

    def __init__(self, state):
        self._state = state


class ModifiableHelper(Helper):
    """
    Allow a L{ConfigurationState}s to be modified.
    """

    def modify(self):
        return ModifiedState(self._state._data, self._state._proxy,
                             self._state._uisettings)


class UnloadableHelper(Helper):
    """
    Disallow loading of data into a L{ConfigurationModel}.
    """

    def load_data(self, asynchronous=True, exit_method=None):
        raise StateError("A ConfiguratiomModel in a " +
                         self.__class__.__name__ +
                         " cannot be transitioned via load_data()")


class UnmodifiableHelper(Helper):
    """
    Disallow modification of a L{ConfigurationState}.
    """

    def modify(self):
        raise StateError("A ConfigurationModel in " +
                         self.__class__.__name__ +
                         " cannot transition via modify()")


class RevertableHelper(Helper):
    """
    Allow reverting of a L{ConfigurationModel}.
    """

    def revert(self):
        return InitialisedState(self._state._data, self._state._proxy,
                                self._state._uisettings)


class UnrevertableHelper(Helper):
    """
    Disallow reverting of a L{ConfigurationModel}.
    """

    def revert(self):
        raise StateError("A ConfigurationModel in " +
                         self.__class__.__name__ +
                         " cannot transition via revert()")


class PersistableHelper(Helper):
    """
    Allow a L{ConfigurationModel} to persist.
    """

    def _save_to_uisettings(self):
        """
        Persist full content to the L{UISettings} object.
        """
        self._state._uisettings.set_management_type(
            self._state.get(MANAGEMENT_TYPE))
        self._state._uisettings.set_computer_title(
            self._state.get(COMPUTER_TITLE))
        self._state._uisettings.set_hosted_account_name(
            self._state.get(HOSTED, ACCOUNT_NAME))
        self._state._uisettings.set_hosted_password(
            self._state.get(HOSTED, PASSWORD))
        self._state._uisettings.set_local_landscape_host(
            self._state.get(LOCAL, LANDSCAPE_HOST))
        self._state._uisettings.set_local_account_name(
            self._state.get(LOCAL, ACCOUNT_NAME))
        self._state._uisettings.set_local_password(
            self._state.get(LOCAL, PASSWORD))

    def _save_to_config(self):
        """
        Persist the subset of the data we want to make live to the actual
        configuration file.
        """
        hosted = self._state.get(MANAGEMENT_TYPE)
        if hosted is NOT_MANAGED:
            pass
        else:
            if hosted == CANONICAL_MANAGED:
                first_key = HOSTED
            else:
                first_key = LOCAL
            self._state._proxy.url = derive_url_from_host_name(
                self._state.get(first_key, LANDSCAPE_HOST))
            self._state._proxy.ping_url = derive_ping_url_from_host_name(
                self._state.get(first_key, LANDSCAPE_HOST))
            self._state._proxy.account_name = self._state.get(
                first_key, ACCOUNT_NAME)
            self._state._proxy.registration_key = self._state.get(
                first_key, PASSWORD)
            self._state._proxy.computer_title = self._state.get(COMPUTER_TITLE)
            self._state._proxy.write()

    def persist(self):
        self._save_to_uisettings()
        self._save_to_config()
        return InitialisedState(self._state._data, self._state._proxy,
                                self._state._uisettings)


class UnpersistableHelper(Helper):
    """
    Disallow persistence of a L{ConfigurationModel}.
    """

    def persist(self):
        raise StateError("A ConfiguratonModel in " +
                         self.__class__.__name__ +
                         " cannot be transitioned via persist().")


class ExitedState(ConfigurationState):
    """
    The terminal state of L{ConfigurationModel}, you can't do anything further
    once this state is reached.
    """
    def __init__(self, data, proxy, uisettings, exit_method=None,
                 asynchronous=True):
        super(ExitedState, self).__init__(None, None, None)
        if callable(exit_method):
            exit_method()
        else:
            proxy.exit(asynchronous=asynchronous)
        self._unloadable_helper = UnloadableHelper(self)
        self._unmodifiable_helper = UnmodifiableHelper(self)
        self._unrevertable_helper = UnrevertableHelper(self)
        self._unpersistable_helper = UnpersistableHelper(self)

    def load_data(self, asynchronous=True, exit_method=None):
        return self._unloadable_helper.load_data(asynchronous=asynchronous,
                                                 exit_method=exit_method)

    def modify(self):
        return self._unmodifiable_helper.modify()

    def revert(self):
        return self._unrevertable_helper.revert()

    def persist(self):
        return self._unpersistable_helper.persist()

    def exit(self, asynchronous=True):
        return self


class ModifiedState(ConfigurationState):
    """
    The state of a L{ConfigurationModel} whenever the user has modified some
    data but hasn't yet L{persist}ed or L{revert}ed.
    """

    def __init__(self, data, proxy, uisettings):
        super(ModifiedState, self).__init__(data, proxy, uisettings)
        self._modifiable_helper = ModifiableHelper(self)
        self._revertable_helper = RevertableHelper(self)
        self._persistable_helper = PersistableHelper(self)

    def modify(self):
        return self._modifiable_helper.modify()

    def revert(self):
        return self._revertable_helper.revert()

    def persist(self):
        return self._persistable_helper.persist()


class InitialisedState(ConfigurationState):
    """
    The state of the L{ConfigurationModel} as initially presented to the
    user. Baseline data should have been loaded from the real configuration
    data, any persisted user data should be loaded into blank values and
    finally defaults should be applied where necessary.
    """

    def __init__(self, data, proxy, uisettings):
        super(InitialisedState, self).__init__(data, proxy, uisettings)
        self._modifiable_helper = ModifiableHelper(self)
        self._unrevertable_helper = UnrevertableHelper(self)
        self._unpersistable_helper = UnpersistableHelper(self)
        self._load_uisettings_data()
        if not self._load_live_data():
            raise TransitionError("Authentication Failure")

    def _load_uisettings_data(self):
        """
        Load the complete set of dialog data from L{UISettings}.
        """
        hosted = self._uisettings.get_management_type()
        self.set(MANAGEMENT_TYPE, hosted)
        computer_title = self._uisettings.get_computer_title()
        if computer_title:
            self.set(COMPUTER_TITLE, computer_title)
        self.set(HOSTED, ACCOUNT_NAME,
                 self._uisettings.get_hosted_account_name())
        self.set(HOSTED, PASSWORD, self._uisettings.get_hosted_password())
        self.set(LOCAL, LANDSCAPE_HOST,
                 self._uisettings.get_local_landscape_host())
        local_account_name = self._uisettings.get_local_account_name()
        if local_account_name:
            self.set(LOCAL, ACCOUNT_NAME, local_account_name)
        self.set(LOCAL, PASSWORD, self._uisettings.get_local_password())

    def _load_live_data(self):
        """
        Load the current live subset of data from the configuration file.
        """
        if self._proxy.load(None):
            computer_title = self._proxy.computer_title
            if computer_title:
                self.set(COMPUTER_TITLE, computer_title)
            url = self._proxy.url
            if url.find(HOSTED_LANDSCAPE_HOST) > -1:
                self.set(HOSTED, ACCOUNT_NAME, self._proxy.account_name)
                self.set(HOSTED, PASSWORD, self._proxy.registration_key)
            else:
                self.set(LOCAL, LANDSCAPE_HOST,
                         derive_server_host_name_from_url(url))
                if self._proxy.account_name != "":
                    self.set(LOCAL, ACCOUNT_NAME, self._proxy.account_name)
            return True
        else:
            return False

    def load_data(self, asynchronous=True, exit_method=None):
        return self

    def modify(self):
        return self._modifiable_helper.modify()

    def revert(self):
        return self._unrevertable_helper.revert()

    def persist(self):
        return self._unpersistable_helper.persist()


class VirginState(ConfigurationState):
    """
    The state of the L{ConfigurationModel} before any actions have been taken
    upon it.
    """

    def __init__(self, proxy, uisettings):
        super(VirginState, self).__init__(DEFAULT_DATA, proxy, uisettings)
        self._unmodifiable_helper = UnmodifiableHelper(self)
        self._unrevertable_helper = UnrevertableHelper(self)
        self._unpersistable_helper = UnpersistableHelper(self)

    def load_data(self, asynchronous=True, exit_method=None):
        try:
            return InitialisedState(self._data, self._proxy, self._uisettings)
        except TransitionError:
            return ExitedState(self._data, self._proxy, self._uisettings,
                               asynchronous=asynchronous,
                               exit_method=exit_method)

    def modify(self):
        return self._unmodifiable_helper.modify()

    def revert(self):
        return self._unrevertable_helper.revert()

    def persist(self):
        return self._unpersistable_helper.persist()


class ConfigurationModel(object):
    """
    L{ConfigurationModel} presents a model of configuration as the UI
    requirements describe it (separate values for the Hosted and Local
    configurations) as opposed to the real structure of the configuration
    file.  This is intended to achieve the following:

       1. Allow the expected behaviour in the UI without changing the live
          config file.
       2. Supersede the overly complex logic in the controller layer with a
          cleaner state pattern.

    The allowable state transitions are:

       VirginState      --(load_data)--> InitialisedState
       VirginState      --(load_data)--> ExitedState
       VirginState      --(exit)-------> ExitedState
       InitialisedState --(modify)-----> ModifiedState
       InitialisedState --(exit)-------> ExitedState
       ModifiedState    --(revert)-----> InitialisedState
       ModifiedState    --(modify)-----> ModifiedState
       ModifiedState    --(persist)----> InitialisedState
       ModifiedState    --(exit)-------> ExitedState
    """

    def __init__(self, proxy=None, proxy_loadargs=[], uisettings=None):
        if not proxy:
            proxy = ConfigurationProxy(loadargs=proxy_loadargs)
        self._current_state = VirginState(proxy, uisettings)

    def get_state(self):
        """
        Expose the underlying L{ConfigurationState}, for testing purposes.
        """
        return self._current_state

    def load_data(self, asynchronous=True, exit_method=None):
        self._current_state = self._current_state.load_data(
            asynchronous=asynchronous, exit_method=exit_method)
        return isinstance(self._current_state, InitialisedState)

    def modify(self):
        self._current_state = self._current_state.modify()

    def revert(self):
        self._current_state = self._current_state.revert()

    def persist(self):
        self._current_state = self._current_state.persist()

    def _get_management_type(self):
        return self._current_state.get(MANAGEMENT_TYPE)

    def _set_management_type(self, value):
        self._current_state.set(MANAGEMENT_TYPE, value)

    management_type = property(_get_management_type, _set_management_type)

    def _get_computer_title(self):
        return self._current_state.get(COMPUTER_TITLE)

    def _set_computer_title(self, value):
        self._current_state.set(COMPUTER_TITLE, value)

    computer_title = property(_get_computer_title, _set_computer_title)

    def _get_hosted_landscape_host(self):
        return self._current_state.get(HOSTED, LANDSCAPE_HOST)

    hosted_landscape_host = property(_get_hosted_landscape_host)

    def _get_local_landscape_host(self):
        return self._current_state.get(LOCAL, LANDSCAPE_HOST)

    def _set_local_landscape_host(self, value):
        self._current_state.set(LOCAL, LANDSCAPE_HOST, value)

    local_landscape_host = property(_get_local_landscape_host,
                                    _set_local_landscape_host)

    def _get_hosted_account_name(self):
        return self._current_state.get(HOSTED, ACCOUNT_NAME)

    def _set_hosted_account_name(self, value):
        self._current_state.set(HOSTED, ACCOUNT_NAME, value)

    hosted_account_name = property(_get_hosted_account_name,
                                   _set_hosted_account_name)

    def _get_local_account_name(self):
        return self._current_state.get(LOCAL, ACCOUNT_NAME)

    def _set_local_account_name(self, value):
        self._current_state.set(LOCAL, ACCOUNT_NAME, value)

    local_account_name = property(_get_local_account_name,
                                   _set_local_account_name)

    def _get_hosted_password(self):
        return self._current_state.get(HOSTED, PASSWORD)

    def _set_hosted_password(self, value):
        self._current_state.set(HOSTED, PASSWORD, value)

    hosted_password = property(_get_hosted_password,
                               _set_hosted_password)

    def _get_local_password(self):
        return self._current_state.get(LOCAL, PASSWORD)

    def _set_local_password(self, value):
        self._current_state.set(LOCAL, PASSWORD, value)

    local_password = property(_get_local_password,
                              _set_local_password)

    def _get_is_modified(self):
        return isinstance(self.get_state(), ModifiedState)

    is_modified = property(_get_is_modified)

    def get_config_filename(self):
        return self._current_state.get_config_filename()

    def exit(self, asynchronous=True):
        self._current_state.exit(asynchronous=asynchronous)
