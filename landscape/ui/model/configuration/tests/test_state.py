from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.state import (
    ConfigurationModel, StateError, VirginState, InitialisedState,
    TestedGoodState, TestedBadState, ModifiedState, IS_HOSTED, HOSTED,
    HOSTED_LANDSCAPE_HOST, LANDSCAPE_HOST)
from landscape.ui.tests.helpers import ConfigurationProxyHelper


class ConfigurationModelTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""
        super(ConfigurationModelTest, self).setUp()
    
    def tearDown(self):
        super(ConfigurationModelTest, self).tearDown()
        self.proxy = None

    def test_get(self):
        """
        Test that L{get} correctly extracts data from the internal data storage
        of the L{ConfigurationState}s associated with a L{ConfigurationModel}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        state = model.get_state()
        self.assertEqual(True, state.get(IS_HOSTED))
        self.assertEqual(HOSTED_LANDSCAPE_HOST, state.get(HOSTED, LANDSCAPE_HOST))
        self.assertRaises(TypeError, state.get, IS_HOSTED, HOSTED, LANDSCAPE_HOST)
        self.assertRaises(KeyError, state.get, LANDSCAPE_HOST)
        self.assertRaises(KeyError, state.get, IS_HOSTED, LANDSCAPE_HOST)

    def test_set(self):
        """
        Test that L{set} correctly sets data in the internal data storage of
        the L{ConfigurationState}s associated with a L{ConfigurationModel}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        state = model.get_state()
        state.set(IS_HOSTED, True)
        self.assertTrue(state.get(IS_HOSTED))
        state.set(IS_HOSTED, False)

    def test_virginal(self):
        """
        Test that the L{ConfigurationModel} is created with default data.  This
        should be managed via L{VirginState} (hence the name), but this should
        not be exposed and is not explicitly tested here (see
        L{StateTransitionTest}).
        """
        model = ConfigurationModel(proxy=self.proxy)
        self.assertTrue(model.is_hosted)
        self.assertEqual(HOSTED_LANDSCAPE_HOST, model.hosted_landscape_host)
        self.assertEqual("", model.local_landscape_host)
        self.assertEqual("", model.hosted_account_name)
        self.assertEqual("", model.local_account_name)
        self.assertEqual("", model.hosted_password)
        

class ConfigurationModelHostedTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = "[client]\n" \
            "data_path = /var/lib/landscape/client/\n" \
            "http_proxy = http://proxy.localdomain:3192\n" \
            "tags = a_tag\n" \
            "url = https://landscape.canonical.com/message-system\n" \
            "account_name = foo\n" \
            "registration_password = boink\n" \
            "computer_title = baz\n" \
            "https_proxy = https://proxy.localdomain:6192\n" \
            "ping_url = http://landscape.canonical.com/ping\n"

        super(ConfigurationModelHostedTest, self).setUp()


    def test_initialised_hosted(self):
        """
        Test the L{ConfigurationModel} is correctly initialised from a proxy
        and defaults with hosted data.
        """
        model = ConfigurationModel(proxy=self.proxy)
        model.load_data()
        self.assertTrue(model.is_hosted)
        self.assertEqual("landscape.canonical.com",
                         model.hosted_landscape_host)
        self.assertEqual("", model.local_landscape_host)
        self.assertEqual("foo", model.hosted_account_name)
        self.assertEqual("", model.local_account_name)
        self.assertEqual("boink", model.hosted_password)
        
        

class StateTransitionTest(LandscapeTest):
    """
    Test that we make the correct state transitions when taking actions on the
    L{ConfigurationModel}.
    """

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""
        super(StateTransitionTest, self).setUp()
    
    def test_load_data_transitions(self):
        """
        Test that the L{ConfigurationModel} correctly changes state as we call
        L{load_data}.
        """
        model = ConfigurationModel(proxy=self.proxy)
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
        model = ConfigurationModel(proxy=self.proxy)
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
        model = ConfigurationModel(proxy=self.proxy, test_method=test_succeed)
        model.load_data()
        model.test()
        self.assertRaises(StateError, model.load_data)
        model = ConfigurationModel(proxy=self.proxy, test_method=test_fail)
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
        model = ConfigurationModel(proxy=self.proxy, test_method=test_succeed)
        model.load_data()
        model.test()
        self.assertTrue(isinstance(model.get_state(), TestedGoodState))
        model = ConfigurationModel(proxy=self.proxy, test_method=test_fail)
        model.load_data()
        model.test()
        self.assertTrue(isinstance(model.get_state(), TestedBadState))

    def test_modifying_a_virgin_raises(self):
        """
        Test that attempting a L{modify} a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        self.assertRaises(StateError, model.modify)

    def test_initialised_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{InitialisedState}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        model.load_data()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_modified_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{ModifiedState}.
        """
        model = ConfigurationModel(proxy=self.proxy)
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
        model = ConfigurationModel(proxy=self.proxy)
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
        model = ConfigurationModel(proxy=self.proxy, test_method=test_succeed)
        model.load_data()
        model.test()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model = ConfigurationModel(proxy=self.proxy, test_method=test_fail)
        model.load_data()
        model.test()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_reverting_a_virgin_raises(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        self.assertRaises(StateError, model.revert)
        
        
    def test_initialiased_state_is_unrevertable(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{InitialisedState} raises a L{StateError}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        model.load_data()
        self.assertRaises(StateError, model.revert)

    def test_modified_state_is_revertable(self):
        """
        Test that a L{ConfigurationModel} in L{ModifiedState} can be
        transitioned via L{revert} to L{InitialisedState}.
        """
        model = ConfigurationModel(proxy=self.proxy)
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
        model = ConfigurationModel(proxy=self.proxy, test_method=test_succeed)
        model.load_data()
        model.test()
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        model = ConfigurationModel(proxy=self.proxy, test_method=test_fail)
        model.load_data()
        model.test()
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))

    def test_persisting_a_virgin_raises(self):
        """
        Test that a L{ConfigurationModel} in L{VirginState} will raise a
        L{StateError} when you attempt to transition it with L{persist}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        self.assertRaises(StateError, model.persist)

    def test_persisting_initialised_state_raises(self):
        """
        Test that a L{ConfigurationModel} in L{IntialisedState} will raise a
        L{StateError} when you attempt to transition it with L{persist}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        model.load_data()
        self.assertRaises(StateError, model.persist)

    def test_persisting_modified_state_raises(self):
        """
        Test that a L{ConfigurationModel} in L{InitialisedState} will raise a 
        L{StateError} when you attempt to transition it with L{persist}.
        """
        model = ConfigurationModel(proxy=self.proxy)
        model.load_data()
        model.modify()
        self.assertRaises(StateError, model.persist)

    def test_persisting_tested_bad_state_raises(self):
        """
        Test that a L{ConfigurationModel} in L{TestedBadState} will raise a
        L{StateError} when you attempt to transition it with L{persist}.
        """
        test_fail = lambda: False
        model = ConfigurationModel(proxy=self.proxy, test_method=test_fail)
        model.load_data()
        model.test()
        self.assertRaises(StateError, model.persist)

    def test_persist_tested_good_state(self):
        """
        Test that a L{ConfigurationModel} in L{TestedGoodState} can be
        transitioned via L{persist} to a L{IntialisedState}.
        """
        test_succeed = lambda: True
        model = ConfigurationModel(proxy=self.proxy, test_method=test_succeed)
        model.load_data()
        model.test()
        model.persist()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
