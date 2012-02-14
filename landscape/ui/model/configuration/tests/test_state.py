from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.state import (
    ConfigurationModel, StateError, VirginState, InitialisedState,
    TestedGoodState, TestedBadState)


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
        
