import copy

from landscape.ui.model.configuration.proxy import ConfigurationProxy


HOSTED_LANDSCAPE_HOST = "landscape.canonical.com"
LOCAL_LANDSCAPE_HOST = ""

HOSTED_ACCOUNT_NAME = ""
LOCAL_ACCOUNT_NAME = ""

HOSTED_PASSWORD = ""
LOCAL_PASSWORD = ""

HOSTED = "hosted"
LOCAL = "local"
IS_HOSTED = "is_hosted"
LANDSCAPE_HOST = "landscape_host"
ACCOUNT_NAME = "account_name"
PASSWORD = "password"
DEFAULT_DATA = {
    IS_HOSTED: True,
    HOSTED: {
        LANDSCAPE_HOST: HOSTED_LANDSCAPE_HOST,
        ACCOUNT_NAME: HOSTED_ACCOUNT_NAME,
        PASSWORD: HOSTED_PASSWORD,
        },
    LOCAL: {
        LANDSCAPE_HOST: LOCAL_LANDSCAPE_HOST,
        ACCOUNT_NAME: LOCAL_ACCOUNT_NAME,
        PASSWORD: LOCAL_PASSWORD,
        }
}


def derive_server_host_name_from_url(url):
    "Extract the hostname part from a URL."
    try:
        without_protocol = url[url.index("://") + 3:]
    except ValueError:
        without_protocol = url
    try:
        return without_protocol[:without_protocol.index("/")]
    except ValueError:
        return without_protocol


def derive_url_from_host_name(host_name):
    "Extrapolate a url from a host name."
    #Reuse this code to make sure it's a proper host name
    host_name = derive_server_host_name_from_url(host_name)
    return "https://" + host_name + "/message-system"


def derive_ping_url_from_host_name(host_name):
    "Extrapolate a ping_url from a host name."
    #Reuse this code to make sure it's a proper host name
    host_name = derive_server_host_name_from_url(host_name)
    return "http://" + host_name + "/ping"


class StateError(Exception):
    """
    An exception that is raised when there is an error relating to the current
    state.
    """


class ConfigurationState(object):
    """
    Base class for states used in the L{ConfigurationModel}.
    """
    
    def __init__(self, data, proxy, uisettings):
        self._data = copy.deepcopy(data)
        self._proxy = proxy
        self._uisettings = uisettings

    def get(self, *args):
        arglen = len(args)
        if arglen > 2 or arglen == 0:
            raise TypeError,  "get() takes either 1 or 2 keys (%d given)" % \
                arglen
        if arglen == 2:
            sub_dict = None
            if args[0] in [HOSTED, LOCAL]:
                sub_dict = self._data.get(args[0], {})
            sub_dict = self._data[args[0]]
            if not isinstance(sub_dict, dict):
                raise KeyError, "Compound key [%s][%s] is invalid. " + \
                    "The data type returned from the first index was %s." % \
                    sub_dict.__class__.__name__
            return sub_dict.get(args[1], None)
        else:
            if args[0] == IS_HOSTED:
                return self._data.get(args[0], None)
            else:
                raise KeyError, "Key [%s] is invalid. " % args[0]
                

    def set(self, *args):
        arglen = len(args)
        if arglen < 2 or arglen > 3:
            raise TypeError,  "set() takes either 1 or 2 keys and exactly" +\
                " 1 value (%d arguments given)" % arglen
        if arglen == 2: 
            self._data[args[0]] = args[1]
        else:
            sub_dict = None
            if args[0] in [HOSTED, LOCAL]:
                sub_dict = self._data.get(args[0], {})
            if not isinstance(sub_dict, dict):
                raise KeyError, "Compound key [%s][%s] is invalid. " + \
                    "The data type returned from the first index was %s." % \
                    sub_dict.__class__.__name__
            sub_dict[args[1]] = args[2]
            self._data[args[0]] = sub_dict
            
    def load_data(self):
        raise NotImplementedError

    def test(self, test_method):
        raise NotImplementedError
    
    def modify(self):
        raise NotImplementedError

    def revert(self):
        raise NotImplementedError

    def persist(self):
        raise NotImplementedError


class Helper(object):
    """
    Base class for all state transition helpers.

    It is assumed that the Helper classes are "friends" of the
    L{ConfigurationState} classes and can have some knowledge of their
    internals.  They shouldn't be visible to users of the
    L{ConfigurationState}s and in general we should avoid seeing the
    L{ConfigurationState}s _data attribute outside this module.
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
    
    def load_data(self):
        raise StateError, "A ConfiguratiomModel in a " + \
            self._state.__class__.__name__ + \
            " cannot be transitioned via load_data()"


class UnmodifiableHelper(Helper):
    """
    Disallow modification of a L{ConfigurationState}.
    """

    def modify(self):
        raise StateError, "A ConfigurationModel in " + \
            self._state.__class__.__name__ + " cannot transition via modify()"


class TestableHelper(Helper):
    """
    Allow testing of a L{ConfigurationModel}.
    """

    def test(self, test_method):
        if test_method():
            return TestedGoodState(self._state._data, self._state._proxy,
                                   self._state._uisettings)
        else:
            return TestedBadState(self._state._data, self._state._proxy,
                                  self._state._uisettings)


class UntestableHelper(Helper):
    """
    Disallow testing of a L{ConfigurationModel}.
    """

    def test(self, test_method):
        raise StateError, "A ConfigurationModel in " + \
            self._state.__class__.__name__ + " cannot transition via test()"


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
        raise StateError, "A ConfigurationModel in " + \
            self._state.__class__.__name__ + " cannot transition via revert()"


class PersistableHelper(Helper):
    """
    Allow a L{ConfigurationModel} to persist.
    """

    def persist(self):
        return InitialisedState(self._state._data, self._state._proxy,
                                self._state._uisettings)


class UnpersistableHelper(Helper):
    """
    Disallow persistence of a L{ConfigurationModel}.
    """

    def persist(self):
        raise StateError, "A ConfiguratonModel in " + \
            self._state.__class__.__name__ + \
            " cannot be transitioned via persist()."


class ModifiedState(ConfigurationState):
    """
    The state of a L{ConfigurationModel} whenever the user has modified some
    data but hasn't yet L{test}ed or L{revert}ed.
    """
    
    def __init__(self, data, proxy, uisettings):
        super(ModifiedState, self).__init__(data, proxy, uisettings)
        self.modifiable_helper = ModifiableHelper(self)
        self.revertable_helper = RevertableHelper(self)
        self.testable_helper = TestableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
        self._save_to_uisettings()

    def _save_to_uisettings(self):
        self._uisettings.set_is_hosted(self.get(IS_HOSTED))
    
    def modify(self):
        return self.modifiable_helper.modify()

    def revert(self):
        return self.revertable_helper.revert()

    def test(self, test_method):
        return self.testable_helper.test(test_method)

    def persist(self):
        return self.unpersistable_helper.persist()


class TestedState(ConfigurationState):
    """
    A superclass for the two possible L{TestedStates} (L{TestedGoodState} and
    L{TestedBadState}).
    """

    def __init__(self, data, proxy, uisettings):
        super(TestedState, self).__init__(data, proxy, uisettings)
        self.untestable_helper = UntestableHelper(self)
        self.unloadable_helper = UnloadableHelper(self)
        self.modifiable_helper = ModifiableHelper(self)
        self.revertable_helper = RevertableHelper(self)
    
    def test(self, test_method):
        return self.untestable_helper.test(test_method)

    def load_data(self):
        return self.unloadable_helper.load_data()

    def modify(self):
        return self.modifiable_helper.modify()

    def revert(self):
        return self.revertable_helper.revert()


class TestedBadState(TestedState):
    """
    The state of a L{ConfigurationModel} after it has been L{test}ed but that
    L{test} has failed for some reason.
    """

    def __init__(self, data, proxy, uisettings):
        super(TestedBadState, self).__init__(data, proxy, uisettings)
        self.unpersistable_helper = UnpersistableHelper(self)

    def persist(self):
        return self.unpersistable_helper.persist()


class TestedGoodState(TestedState):
    """
    The state of a L{ConfigurationModel} after it has been L{test}ed
    successfully.
    """
    
    def __init__(self, data, proxy, uisettings):
        super(TestedGoodState, self).__init__(data, proxy, uisettings)
        self.persistable_helper = PersistableHelper(self)

    def persist(self):
        return self.persistable_helper.persist()


class InitialisedState(ConfigurationState):
    """
    The state of the L{ConfigurationModel} as initially presented to the
    user. Baseline data should have been loaded from the real configuration
    data, any persisted user data should be loaded into blank values and
    finally defaults should be applied where necessary.
    """

    def __init__(self, data, proxy, uisettings):
        super(InitialisedState, self).__init__(data, proxy, uisettings)
        self.modifiable_helper = ModifiableHelper(self)
        self.unrevertable_helper = UnrevertableHelper(self)
        self.testable_helper = TestableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
        self._load_uisettings_data()
        self._load_live_data()

    def _load_uisettings_data(self):
        self.set(IS_HOSTED, self._uisettings.get_is_hosted())
        self.set(HOSTED, LANDSCAPE_HOST,
                 self._uisettings.get_hosted_landscape_host())
        self.set(HOSTED, ACCOUNT_NAME,
                 self._uisettings.get_hosted_account_name())
        self.set(HOSTED, PASSWORD, self._uisettings.get_hosted_password())
        self.set(LOCAL, LANDSCAPE_HOST,
                 self._uisettings.get_local_landscape_host())
        self.set(LOCAL, ACCOUNT_NAME,
                 self._uisettings.get_local_account_name())
        self.set(LOCAL, PASSWORD, self._uisettings.get_local_password())

    def _load_live_data(self):
        self._proxy.load(None)
        url = self._proxy.url
        if url.find(HOSTED_LANDSCAPE_HOST) > -1:
            self.set(IS_HOSTED, True)
            self.set(HOSTED, ACCOUNT_NAME, self._proxy.account_name)
            self.set(HOSTED, PASSWORD, self._proxy.registration_password)
        else:
            self.set(IS_HOSTED, False)
            self.set(LOCAL, LANDSCAPE_HOST,
                     derive_server_host_name_from_url(url) )
            self.set(LOCAL, ACCOUNT_NAME, self._proxy.account_name)
            
    def load_data(self):
        return self

    def modify(self):
        return self.modifiable_helper.modify()

    def revert(self):
        return self.unrevertable_helper.revert()

    def test(self, test_method):
        return self.testable_helper.test(test_method)

    def persist(self):
        return self.unpersistable_helper.persist()


class VirginState(ConfigurationState):
    """
    The state of the L{ConfigurationModel} before any actions have been taken
    upon it.
    """
    
    def __init__(self, proxy, uisettings):
        super(VirginState, self).__init__(DEFAULT_DATA, proxy, uisettings)
        self.untestable_helper = UntestableHelper(self)
        self.unmodifiable_helper = UnmodifiableHelper(self)
        self.unrevertable_helper = UnrevertableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
    
    def load_data(self):
        return InitialisedState(self._data, self._proxy, self._uisettings)

    def test(self, test_method):
        return self.untestable_helper.test(test_method)

    def modify(self):
        return self.unmodifiable_helper.modify()

    def revert(self):
        return self.unrevertable_helper.revert()

    def persist(self):
        return self.unpersistable_helper.persist()


class ConfigurationModel(object):
    
    def __init__(self, test_method=None, proxy=None, proxy_loadargs=[],
                 uisettings=None):
        if not proxy:
            proxy = ConfigurationProxy(loadargs=proxy_loadargs)
        self._current_state = VirginState(proxy, uisettings)
        if test_method:
            self._test_method = test_method
        else:
            self._test_method = self._test

    def _test(self):
        # TODO, dump this and use something real
        return True
    
    def get_state(self):
        """
        Expose the underlying L{ConfigurationState}, for testing purposes.
        """
        return self._current_state

    def load_data(self):
        self._current_state = self._current_state.load_data()
        
    def test(self):
        self._current_state = self._current_state.test(self._test_method)

    def modify(self):
        self._current_state = self._current_state.modify()

    def revert(self):
        self._current_state = self._current_state.revert()
    
    def persist(self):
        self._current_state = self._current_state.persist()

    def _get_is_hosted(self):
        return self._current_state.get(IS_HOSTED)
    
    def _set_is_hosted(self, value):
        self._current_state.set(IS_HOSTED, value)
    
    is_hosted = property(_get_is_hosted, _set_is_hosted)
    
    def _get_hosted_landscape_host(self):
        return self._current_state.get(HOSTED, LANDSCAPE_HOST)

    def _set_hosted_landscape_host(self, value):
        self._current_state.set(HOSTED, LANDSCAPE_HOST, value)

    hosted_landscape_host = property(_get_hosted_landscape_host, 
                                     _set_hosted_landscape_host)

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
