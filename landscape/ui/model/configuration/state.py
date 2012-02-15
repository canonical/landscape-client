import copy


HOSTED_URL = "https://landscape.canonical.com/message"
HOSTED = 0
LOCAL = 1
IS_HOSTED = 2
URL = 0
DEFAULT_DATA = {
    IS_HOSTED: True,
    HOSTED: {
        URL: HOSTED_URL,
        },
    LOCAL: {
        }
}


class StateError(Exception):
    """
    An exception that is raised when there is an error relating to the current
    state.
    """

class ConfigurationState(object):
    """
    Base class for states used in the L{ConfigurationModel}.
    """
    
    def __init__(self, data):
        self._data = copy.copy(data)

    def get(self, name):
        return self._data[name]
        
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
        return ModifiedState(self._state._data)


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
            return TestedGoodState(self._state._data)
        else:
            return TestedBadState(self._state._data)


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
        return InitialisedState(self._state._data)


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
        return InitialisedState(self._state._data)


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
    
    def __init__(self, data):
        super(ModifiedState, self).__init__(data)
        self.modifiable_helper = ModifiableHelper(self)
        self.revertable_helper = RevertableHelper(self)
        self.testable_helper = TestableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
    
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

    def __init__(self, data):
        super(TestedState, self).__init__(data)
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

    def __init__(self, data):
        super(TestedBadState, self).__init__(data)
        self.unpersistable_helper = UnpersistableHelper(self)

    def persist(self):
        return self.unpersistable_helper.persist()


class TestedGoodState(TestedState):
    """
    The state of a L{ConfigurationModel} after it has been L{test}ed
    successfully.
    """
    
    def __init__(self, data):
        super(TestedGoodState, self).__init__(data)
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

    def __init__(self, data):
        super(InitialisedState, self).__init__(data)
        self.modifiable_helper = ModifiableHelper(self)
        self.unrevertable_helper = UnrevertableHelper(self)
        self.testable_helper = TestableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
    
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
    
    def __init__(self):
        super(VirginState, self).__init__(DEFAULT_DATA)
        self.untestable_helper = UntestableHelper(self)
        self.unmodifiable_helper = UnmodifiableHelper(self)
        self.unrevertable_helper = UnrevertableHelper(self)
        self.unpersistable_helper = UnpersistableHelper(self)
    
    def load_data(self):
        return InitialisedState(self._data)

    def test(self, test_method):
        return self.untestable_helper.test(test_method)

    def modify(self):
        return self.unmodifiable_helper.modify()

    def revert(self):
        return self.unrevertable_helper.revert()

    def persist(self):
        return self.unpersistable_helper.persist()


class ConfigurationModel(object):
    
    def __init__(self, test_method=None, proxy=None):
        self._current_state = VirginState()
        if test_method:
            self._test_method = test_method
        else:
            self._test_method = self._test
        if proxy:
            self._proxy = proxy
        else:
            pass

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

    def get_is_hosted(self):
        return self._current_state.get(IS_HOSTED)
