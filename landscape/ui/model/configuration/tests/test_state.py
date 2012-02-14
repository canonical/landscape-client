from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.state import (
    ConfigurationModel, StateError, VirginState, InitialisedState,
    TestedGoodState, TestedBadState, ModifiedState)


class StateTransitionTest(LandscapeTest):
    """
    Test that we make the correct state transitions when taking actions on the
    L{ConfigurationModel}.
    """
    
    def test_load_data_transitions(self):
        """
        Test that the L{ConfigurationModel} correctly changes state as we call
        L{load_data}.
        """
        model = ConfigurationModel()
        self.assertTrue(isinstance(model.get_state(), VirginState))
        model.load_data()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        initialised = model.get_state()
        model.load_data()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        self.assertIs(initialised, model.get_state())
    
    def test_testing_a_virgin_raises(self):
        """
        Test that calling L{test} on a L{ConfigurationModel} in L{VirginState}
        raises an error.
        """
        model = ConfigurationModel()
        self.assertTrue(isinstance(model.get_state(), VirginState))
        self.assertRaises(StateError, model.test)

    def test_load_data_on_tested_state_raises(self):
        """
        Test that calling L{load_data} on a L{ConfigurationModel} in either one
        of the two L{TestedState} subclasses (L{TestedGoodState} or
        L{TestedBadState}) will raise a L{StateError}.
        """
        test_succeed = lambda : True
        test_fail = lambda : False
        model = ConfigurationModel(test_method=test_succeed)
        model.load_data()
        model.test()
        self.assertRaises(StateError, model.load_data)
        model = ConfigurationModel(test_method=test_fail)
        model.load_data()
        model.test()
        self.assertRaises(StateError, model.load_data)
                       
    def test_test_transition(self):
        """
        Test that the L{ConfigurationModel} transitions to a L{TestedGoodState}
        or a L{TestedBadState} when L{test} is called.
        """
        test_succeed = lambda : True
        test_fail = lambda : False
        model = ConfigurationModel(test_method=test_succeed)
        model.load_data()
        model.test()
        self.assertTrue(isinstance(model.get_state(), TestedGoodState))
        model = ConfigurationModel(test_method=test_fail)
        model.load_data()
        model.test()
        self.assertTrue(isinstance(model.get_state(), TestedBadState))

    def test_modifying_a_virgin_raises(self):
        """
        Test that attempting a L{modify} a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        model = ConfigurationModel()
        self.assertRaises(StateError, model.modify)

    def test_initialised_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{InitialisedState}.
        """
        model = ConfigurationModel()
        model.load_data()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_modified_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{ModifiedState}.
        """
        model = ConfigurationModel()
        model.load_data()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_modified_state_is_testable(self):
        """
        Test that the L{ConfigurationModel} can be transitioned via L{test}
        when it is in the L{ModifiedState}.
        """
        model = ConfigurationModel()
        model.load_data()
        model.modify()
        model.test()
        self.assertTrue(isinstance(model.get_state(), TestedGoodState))

    def test_tested_states_are_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in a subclass of L{TestedState}
        (L{TestedGoodState} or L{TestedBadState}).
        """
        test_succeed = lambda : True
        test_fail = lambda : False
        model = ConfigurationModel(test_method=test_succeed)
        model.load_data()
        model.test()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model = ConfigurationModel(test_method=test_fail)
        model.load_data()
        model.test()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_reverting_a_virgin_raises(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        model = ConfigurationModel()
        self.assertRaises(StateError, model.revert)
        
        
    def test_initialiased_state_is_unrevertable(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{InitialisedState} raises a L{StateError}.
        """
        model = ConfigurationModel()
        model.load_data()
        self.assertRaises(StateError, model.revert)

    def test_modified_state_is_revertable(self):
        """
        Test that a L{ConfigurationModel} in L{ModifiedState} can be
        transitioned via L{revert} to L{InitialisedState}.
        """
        model = ConfigurationModel()
        model.load_data()
        model.modify()
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
    
    def test_tested_states_are_revertable(self):
        """
        Test that a L{ConfigurationModel} in one of the two L{TestedState}s can
        be transitioned via L{revert} to L{InitialisedState}.
        """
        test_succeed = lambda : True
        test_fail = lambda : False
        model = ConfigurationModel(test_method=test_succeed)
        model.load_data()
        model.test()
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
