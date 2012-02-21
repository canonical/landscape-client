

class StateError(Exception):
    """
    An exception that is raised when there is an error relating to the current
    state.
    """


class ConfigurationState(object):
    """
    Abstract base class for states used in the L{ConfigurationModel}.
    """

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


class ModifiableHelper(object):
    """
    Allow a L{ConfigurationState}s to be modified.
    """

    def modify(self):
        return ModifiedState()


class UnloadableHelper(object):
    """
    Disallow loading of data into a L{ConfigurationModel}.
    """

    def load_data(self):
        raise StateError("A ConfiguratiomModel in a " +
                         self.__class__.__name__ +
                         " cannot be transitioned via load_data()")


class UnmodifiableHelper(object):
    """
    Disallow modification of a L{ConfigurationState}.
    """

    def modify(self):
        raise StateError("A ConfigurationModel in " +
                         self.__class__.__name__ +
                         " cannot transition via modify()")


class TestableHelper(object):
    """
    Allow testing of a L{ConfigurationModel}.
    """

    def test(self, test_method):
        if test_method():
            return TestedGoodState()
        else:
            return TestedBadState()


class UntestableHelper(object):
    """
    Disallow testing of a L{ConfigurationModel}.
    """

    def test(self, test_method):
        raise StateError("A ConfigurationModel in " +
                         self.__class__.__name__ +
                         " cannot transition via test()")


class RevertableHelper(object):
    """
    Allow reverting of a L{ConfigurationModel}.
    """

    def revert(self):
        return InitialisedState()


class UnrevertableHelper(object):
    """
    Disallow reverting of a L{ConfigurationModel}.
    """

    def revert(self):
        raise StateError("A ConfigurationModel in " +
                         self.__class__.__name__ +
                         " cannot transition via revert()")


class PersistableHelper(object):
    """
    Allow a L{ConfigurationModel} to persist.
    """

    def persist(self):
        return InitialisedState()


class UnpersistableHelper(object):
    """
    Disallow persistence of a L{ConfigurationModel}.
    """

    def persist(self):
        raise StateError("A ConfiguratonModel in " +
                         self.__class__.__name__ +
                         " cannot be transitioned via persist().")


class ModifiedState(ConfigurationState):
    """
    The state of a L{ConfigurationModel} whenever the user has modified some
    data but hasn't yet L{test}ed or L{revert}ed.
    """

    modifiable_helper = ModifiableHelper()
    revertable_helper = RevertableHelper()
    testable_helper = TestableHelper()
    unpersistable_helper = UnpersistableHelper()

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

    untestable_helper = UntestableHelper()
    unloadable_helper = UnloadableHelper()
    modifiable_helper = ModifiableHelper()
    revertable_helper = RevertableHelper()

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

    unpersistable_helper = UnpersistableHelper()

    def persist(self):
        return self.unpersistable_helper.persist()


class TestedGoodState(TestedState):
    """
    The state of a L{ConfigurationModel} after it has been L{test}ed
    successfully.
    """

    persistable_helper = PersistableHelper()

    def persist(self):
        return self.persistable_helper.persist()


class InitialisedState(ConfigurationState):
    """
    The state of the L{ConfigurationModel} as initially presented to the
    user. Baseline data should have been loaded from the real configuration
    data, any persisted user data should be loaded into blank values and
    finally defaults should be applied where necessary.
    """

    modifiable_helper = ModifiableHelper()
    unrevertable_helper = UnrevertableHelper()
    testable_helper = TestableHelper()
    unpersistable_helper = UnpersistableHelper()

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

    untestable_helper = UntestableHelper()
    unmodifiable_helper = UnmodifiableHelper()
    unrevertable_helper = UnrevertableHelper()
    unpersistable_helper = UnpersistableHelper()

    def load_data(self):
        return InitialisedState()

    def test(self, test_method):
        return self.untestable_helper.test(test_method)

    def modify(self):
        return self.unmodifiable_helper.modify()

    def revert(self):
        return self.unrevertable_helper.revert()

    def persist(self):
        return self.unpersistable_helper.persist()


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
       InitialisedState --(modify)-----> ModifiedState
       InitialisedState --(test)-------> TestedGoodState
       InitialisedState --(test)-------> TestedBadState
       ModifiedState    --(revert)-----> InitialisedState
       ModifiedState    --(modify)-----> ModifiedState
       ModifiedState    --(test)-------> TestedGoodState
       ModifiedState    --(test)-------> TestedBadState
       TestedGoodState  --(revert)-----> InitialisedState
       TestedGoodState  --(persist)----> InitialisedState
       TestedGoodState  --(modify)-----> ModifiedState
       TestedBadState   --(revert)-----> InitialisedState
       TestedBadState   --(modify)-----> ModifiedState
    """

    def __init__(self, test_method=None):
        self._current_state = VirginState()
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
