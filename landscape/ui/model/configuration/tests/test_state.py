from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, FakeGSettings, dbus_test_should_skip,
    dbus_skip_message, gobject_skip_message, got_gobject_introspection)

if got_gobject_introspection:
    from landscape.ui.model.configuration.uisettings import UISettings
    import landscape.ui.model.configuration.state
    from landscape.ui.model.configuration.state import (
        ConfigurationModel, StateError, VirginState, InitialisedState,
        ModifiedState, MANAGEMENT_TYPE, HOSTED, LOCAL, HOSTED_LANDSCAPE_HOST,
        LANDSCAPE_HOST, COMPUTER_TITLE)
    from landscape.ui.constants import (
        CANONICAL_MANAGED, LOCAL_MANAGED, NOT_MANAGED)


from landscape.tests.helpers import LandscapeTest


class ConfigurationModelTest(LandscapeTest):
    """
    Test the internal data handling of the L{ConfigurationModel} without
    loading external data.
    """

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.default_data = {"is-hosted": True,
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""
                             }
        self.config_string = ""
        self.default_data = {"management-type": "canonical",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""
                             }
        landscape.ui.model.configuration.state.DEFAULT_DATA[COMPUTER_TITLE] \
            = "bound.to.lose"
        super(ConfigurationModelTest, self).setUp()

    def test_get(self):
        """
        Test that L{get} correctly extracts data from the internal data storage
        of the L{ConfigurationState}s associated with a L{ConfigurationModel}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        state = model.get_state()
        self.assertEqual(NOT_MANAGED, state.get(MANAGEMENT_TYPE))
        self.assertEqual(HOSTED_LANDSCAPE_HOST,
                         state.get(HOSTED, LANDSCAPE_HOST))
        self.assertRaises(TypeError, state.get, MANAGEMENT_TYPE, HOSTED,
                          LANDSCAPE_HOST)
        self.assertRaises(KeyError, state.get, LANDSCAPE_HOST)
        self.assertRaises(KeyError, state.get, MANAGEMENT_TYPE, LANDSCAPE_HOST)

    def test_set(self):
        """
        Test that L{set} correctly sets data in the internal data storage of
        the L{ConfigurationState}s associated with a L{ConfigurationModel}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        state = model.get_state()
        state.set(MANAGEMENT_TYPE, NOT_MANAGED)
        self.assertEqual(NOT_MANAGED, state.get(MANAGEMENT_TYPE))
        state.set(MANAGEMENT_TYPE, CANONICAL_MANAGED)
        self.assertEqual(CANONICAL_MANAGED, state.get(MANAGEMENT_TYPE))
        state.set(MANAGEMENT_TYPE, LOCAL_MANAGED)
        self.assertEqual(LOCAL_MANAGED, state.get(MANAGEMENT_TYPE))
        self.assertEqual("", state.get(LOCAL, LANDSCAPE_HOST))
        state.set(LOCAL, LANDSCAPE_HOST, "goodison.park")
        self.assertEqual("goodison.park", state.get(LOCAL, LANDSCAPE_HOST))

    def test_virginal(self):
        """
        Test that the L{ConfigurationModel} is created with default data.  This
        should be managed via L{VirginState} (hence the name), but this should
        not be exposed and is not explicitly tested here (see
        L{StateTransitionTest}).
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual(NOT_MANAGED, model.management_type)
        self.assertEqual(HOSTED_LANDSCAPE_HOST, model.hosted_landscape_host)
        self.assertEqual("bound.to.lose", model.computer_title)
        self.assertEqual("", model.local_landscape_host)
        self.assertEqual("", model.hosted_account_name)
        self.assertEqual("standalone", model.local_account_name)
        self.assertEqual("", model.hosted_password)

    def test_is_hosted_property(self):
        """
        Test we can use the L{is_hosted} property to set and get that data on
        the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(CANONICAL_MANAGED, model.management_type)
        model.management_type = LOCAL_MANAGED
        self.assertEqual(LOCAL_MANAGED, model.management_type)
        model.management_type = NOT_MANAGED
        self.assertEqual(NOT_MANAGED, model.management_type)

    def test_computer_title_property(self):
        """
        Test that we can use the L{computer_title} property to set and get that
        data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual("bound.to.lose", model.computer_title)
        model.computer_title = "bound.to.win"
        self.assertEqual("bound.to.win", model.computer_title)

    def test_hosted_landscape_host_property(self):
        """
        Test we can use the L{hosted_landscape_host} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual(HOSTED_LANDSCAPE_HOST, model.hosted_landscape_host)
        self.assertRaises(AttributeError, setattr, model,
                          "hosted_landscape_host", "foo")

    def test_hosted_account_name_property(self):
        """
        Test we can use the L{hosted_account_name} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual("", model.hosted_account_name)
        model.hosted_account_name = "foo"
        self.assertEqual("foo", model.hosted_account_name)

    def test_hosted_password_property(self):
        """
        Test we can use the L{hosted_password} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual("", model.hosted_password)
        model.hosted_password = "foo"
        self.assertEqual("foo", model.hosted_password)

    def test_local_landscape_host_property(self):
        """
        Test we can use the L{local_landscape_host} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual("", model.local_landscape_host)
        model.local_landscape_host = "foo"
        self.assertEqual("foo", model.local_landscape_host)

    def test_local_account_name_property(self):
        """
        Test we can use the L{local_account_name} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual("standalone", model.local_account_name)
        model.local_account_name = "foo"
        self.assertEqual("foo", model.local_account_name)

    def test_local_password_property(self):
        """
        Test we can use the L{local_password} property to set and get
        that data on the current L{ConfigurationState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertEqual("", model.local_password)
        model.local_password = "foo"
        self.assertEqual("foo", model.local_password)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class ConfigurationModelHostedTest(LandscapeTest):
    """
    Test the L{ConfigurationModel} is correctly initialised when the live
    configuration is set for a hosted account.

    Note the multilayer data loading:

         1. Internal state is defaulted.
         2. UISettings data is loaded.
         3. Live configuration is loaded.
    """

    helpers = [ConfigurationProxyHelper]

    default_data = {"management-type": "canonical",
                    "computer-title": "bound.to.lose",
                    "hosted-landscape-host": "landscape.canonical.com",
                    "hosted-account-name": "Sparklehorse",
                    "hosted-password": "Vivadixiesubmarinetransmissionplot",
                    "local-landscape-host": "the.local.machine",
                    "local-account-name": "CrazyHorse",
                    "local-password": "RustNeverSleeps"
                    }

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
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(CANONICAL_MANAGED, model.management_type)
        self.assertEqual("landscape.canonical.com",
                         model.hosted_landscape_host)
        self.assertEqual("the.local.machine", model.local_landscape_host)
        self.assertEqual("foo", model.hosted_account_name)
        self.assertEqual("CrazyHorse", model.local_account_name)
        self.assertEqual("boink", model.hosted_password)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class ConfigurationModelLocalTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    default_data = {"management-type": "LDS",
                    "computer-title": "bound.to.lose",
                    "hosted-landscape-host": "landscape.canonical.com",
                    "hosted-account-name": "Sparklehorse",
                    "hosted-password": "Vivadixiesubmarinetransmissionplot",
                    "local-landscape-host": "the.local.machine",
                    "local-account-name": "CrazyHorse",
                    "local-password": "RustNeverSleeps"
                    }

    def setUp(self):
        self.config_string = "[client]\n" \
            "data_path = /var/lib/landscape/client/\n" \
            "http_proxy = http://proxy.localdomain:3192\n" \
            "tags = a_tag\n" \
            "url = https://landscape.localdomain/message-system\n" \
            "account_name = foo\n" \
            "registration_password = boink\n" \
            "computer_title = baz\n" \
            "https_proxy = \n" \
            "ping_url = http://landscape.localdomain/ping\n"

        super(ConfigurationModelLocalTest, self).setUp()

    def test_initialised_local(self):
        """
        Test the L{ConfigurationModel} is correctly initialised from a proxy
        and defaults with local data.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(LOCAL_MANAGED, model.management_type)
        self.assertEqual("landscape.canonical.com",
                         model.hosted_landscape_host)
        self.assertEqual("landscape.localdomain", model.local_landscape_host)
        self.assertEqual("Sparklehorse", model.hosted_account_name)
        self.assertEqual("foo", model.local_account_name)
        self.assertEqual("Vivadixiesubmarinetransmissionplot",
                         model.hosted_password)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class StateTransitionTest(LandscapeTest):
    """
    Test that we make the correct state transitions when taking actions on the
    L{ConfigurationModel}.
    """

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""
        self.default_data = {
            "management-type": "canonical",
            "computer-title": "bound.to.lose",
            "hosted-landscape-host": "landscape.canonical.com",
            "hosted-account-name": "Sparklehorse",
            "hosted-password": "Vivadixiesubmarinetransmissionplot",
            "local-landscape-host": "the.local.machine",
            "local-account-name": "CrazyHorse",
            "local-password": "RustNeverSleeps"
            }
        super(StateTransitionTest, self).setUp()

    def test_load_data_transitions(self):
        """
        Test that the L{ConfigurationModel} correctly changes state as we call
        L{load_data}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertTrue(isinstance(model.get_state(), VirginState))
        model.load_data()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        initialised = model.get_state()
        model.load_data()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        self.assertIs(initialised, model.get_state())

    def test_modifying_a_virgin_raises(self):
        """
        Test that attempting a L{modify} a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertRaises(StateError, model.modify)

    def test_initialised_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{InitialisedState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(CANONICAL_MANAGED, model.management_type)
        model.management_type = LOCAL_MANAGED
        self.assertEqual(LOCAL_MANAGED, model.management_type)
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        self.assertEqual(LOCAL_MANAGED, model.management_type)

    def test_modified_state_is_modifiable(self):
        """
        Test that the L{ConfigurationModel} transitions to L{ModifiedState}
        whenever L{modify} is called on it in L{ModifiedState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))

    def test_reverting_a_virgin_raises(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{VirginState} raises a L{StateError}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertRaises(StateError, model.revert)

    def test_initialiased_state_is_unrevertable(self):
        """
        Test that calling L{revert} on a L{ConfigurationModel} in
        L{InitialisedState} raises a L{StateError}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertRaises(StateError, model.revert)

    def test_modified_state_is_revertable(self):
        """
        Test that a L{ConfigurationModel} in L{ModifiedState} can be
        transitioned via L{revert} to L{InitialisedState}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        model.modify()
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))

    def test_reverting_reverts_data(self):
        """
        Test that transitioning via L{revert} causes the original
        L{InitialisedState} to be restored.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(HOSTED_LANDSCAPE_HOST, model.hosted_landscape_host)
        self.assertEqual("CrazyHorse", model.local_account_name)
        model.local_account_name = "bar"
        model.modify()
        self.assertEqual("bar", model.local_account_name)
        model.revert()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        self.assertEqual("CrazyHorse", model.local_account_name)

    def test_persisting_a_virgin_raises(self):
        """
        Test that a L{ConfigurationModel} in L{VirginState} will raise a
        L{StateError} when you attempt to transition it with L{persist}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.assertRaises(StateError, model.persist)

    def test_persisting_initialised_state_raises(self):
        """
        Test that a L{ConfigurationModel} in L{IntialisedState} will raise a
        L{StateError} when you attempt to transition it with L{persist}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertRaises(StateError, model.persist)

    def test_persisting_modified_is_allowed(self):
        """
        Test that a L{ConfigurationModel} in L{ModifiedState} will allow itself
        to be transitioned with L{persist}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        model.modify()
        model.persist()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))

    def test_persisting_saves_data_to_uisettings(self):
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual(CANONICAL_MANAGED, uisettings.get_management_type())
        self.assertEqual("Sparklehorse", uisettings.get_hosted_account_name())
        self.assertEqual("Vivadixiesubmarinetransmissionplot",
                        uisettings.get_hosted_password())
        self.assertEqual("the.local.machine",
                         uisettings.get_local_landscape_host())
        self.assertEqual("CrazyHorse", uisettings.get_local_account_name())
        self.assertEqual("RustNeverSleeps", uisettings.get_local_password())
        model.management_type = LOCAL_MANAGED
        model.hosted_account_name = "ThomasPaine"
        model.hosted_password = "TheAgeOfReason"
        model.local_landscape_host = "another.local.machine"
        model.local_account_name = "ThomasHobbes"
        model.local_password = "TheLeviathan"
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model.persist()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        self.assertEqual(LOCAL_MANAGED, uisettings.get_management_type())
        self.assertEqual("ThomasPaine", uisettings.get_hosted_account_name())
        self.assertEqual("TheAgeOfReason", uisettings.get_hosted_password())
        self.assertEqual("another.local.machine",
                         uisettings.get_local_landscape_host())
        self.assertEqual("ThomasHobbes", uisettings.get_local_account_name())
        self.assertEqual("TheLeviathan", uisettings.get_local_password())

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class StateTransitionWithExistingConfigTest(LandscapeTest):
    """
    Test that we handle existing configuration data correctly when
    transitioning through L{ConfigurationModel} states.
    """

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = (
            "[client]\n"
            "data_path = /var/lib/landscape/client/\n"
            "http_proxy = http://proxy.localdomain:3192\n"
            "tags = a_tag\n"
            "url = https://landscape.canonical.com/message-system\n"
            "account_name = Sparklehorse\n"
            "registration_password = Vivadixiesubmarinetransmissionplot\n"
            "computer_title = baz\n"
            "https_proxy = https://proxy.localdomain:6192\n"
            "ping_url = http://landscape.canonical.com/ping\n")
        self.default_data = {
            "management-type": "canonical",
            "computer-title": "bound.to.lose",
            "hosted-landscape-host": "landscape.canonical.com",
            "hosted-account-name": "Sparklehorse",
            "hosted-password": "Vivadixiesubmarinetransmissionplot",
            "local-landscape-host": "the.local.machine",
            "local-account-name": "CrazyHorse",
            "local-password": "RustNeverSleeps"
            }
        super(StateTransitionWithExistingConfigTest, self).setUp()

    def test_persisting_saves_data_to_proxy(self):
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        model.load_data()
        self.assertEqual("Sparklehorse", self.proxy.account_name)
        self.assertEqual("Vivadixiesubmarinetransmissionplot",
                        self.proxy.registration_password)
        model.management_type = LOCAL_MANAGED
        model.local_account_name = "ThomasPaine"
        model.local_password = "TheAgeOfReason"
        model.modify()
        self.assertTrue(isinstance(model.get_state(), ModifiedState))
        model.persist()
        self.assertTrue(isinstance(model.get_state(), InitialisedState))
        self.assertEqual(LOCAL_MANAGED, model.management_type)
        self.assertEqual("https://the.local.machine/message-system",
                         self.proxy.url)
        self.assertEqual("http://the.local.machine/ping", self.proxy.ping_url)
        self.assertEqual("ThomasPaine", self.proxy.account_name)
        self.assertEqual("TheAgeOfReason", self.proxy.registration_password)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message
