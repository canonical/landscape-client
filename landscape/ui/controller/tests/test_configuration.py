from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, dbus_test_should_skip, dbus_skip_message,
    FakeGSettings, got_gobject_introspection, gobject_skip_message)

if got_gobject_introspection:
    from landscape.ui.controller.configuration import (
        ConfigController, ConfigControllerLockError)
    import landscape.ui.model.configuration.state
    from landscape.ui.model.configuration.state import (
        ConfigurationModel, COMPUTER_TITLE)
    from landscape.ui.model.configuration.uisettings import UISettings
    from landscape.ui.controller.configuration import ConfigController

from landscape.tests.helpers import LandscapeTest


class ConfigControllerTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = "\n".join(
            ["[client]",
             "data_path = /var/lib/landscape/client/",
             "http_proxy = http://proxy.localdomain:3192",
             "tags = a_tag",
             "url = https://landscape.canonical.com/message-system",
             "account_name = foo",
             "registration_password = bar",
             "computer_title = baz",
             "https_proxy = https://proxy.localdomain:6192",
             "ping_url = http://landscape.canonical.com/ping"
             ])

        self.default_data = {"management-type": "canonical",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""
                             }

        super(ConfigControllerTest, self).setUp()
        landscape.ui.model.configuration.state.DEFAULT_DATA[COMPUTER_TITLE] \
            = "me.here.com"
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.controller = ConfigController(model)
        self.controller.load()

    def test_init(self):
        """
        Test that when we create a controller it has initial state read in
        directly from the configuration file.
        """
        self.controller.load()
        self.assertEqual("baz", self.controller.computer_title)
        self.assertTrue(self.controller.management_type)
        self.assertEqual("landscape.canonical.com",
                         self.controller.hosted_landscape_host)
        self.assertEqual("foo", self.controller.hosted_account_name)
        self.assertEqual("bar", self.controller.hosted_password)
        self.assertEqual("", self.controller.local_landscape_host)
        self.assertEqual("standalone", self.controller.local_account_name)
        self.assertEqual("", self.controller.local_password)

    def test_set_hosted_account_name(self):
        """
        Test that we can set the L{hosted_account_name} property.
        """
        self.controller.load()
        self.assertEqual(self.controller.hosted_account_name, "foo")
        self.controller.hosted_account_name = "shoe"
        self.assertEqual(self.controller.hosted_account_name, "shoe")

    def test_set_local_account_name(self):
        """
        Test that we can set the L{local_account_name} property.
        """
        self.controller.load()
        self.assertEqual("standalone", self.controller.local_account_name)
        self.controller.local_account_name = "shoe"
        self.assertEqual(self.controller.local_account_name, "shoe")

    def test_set_hosted_password(self):
        """
        Test that we can set the L{hosted_password} property.
        """
        self.controller.load()
        self.assertEqual(self.controller.hosted_password, "bar")
        self.controller.hosted_password = "nucker"
        self.assertEqual(self.controller.hosted_password, "nucker")

    def test_set_local_password(self):
        """
        Test that we can set the L{local_password} property.
        """
        self.controller.load()
        self.assertEqual(self.controller.local_password, "")
        self.controller.local_password = "nucker"
        self.assertEqual(self.controller.local_password, "nucker")

    def test_set_local_landscape_host(self):
        """
        Test that we can set the L{local_landscape_host} property.
        """
        self.controller.load()
        self.assertEqual("", self.controller.local_landscape_host)
        self.controller.local_landscape_host = "smelly.pants"
        self.assertEqual(self.controller.local_landscape_host, "smelly.pants")

    def test_revert(self):
        """
        Test that we can revert the controller to it's initial state.
        """
        self.controller.load()
        self.assertEqual(self.controller.hosted_account_name, "foo")
        self.controller.hosted_account_name = "Hildaborg"
        self.assertEqual(self.controller.hosted_account_name, "Hildaborg")
        self.controller.revert()
        self.assertEqual(self.controller.hosted_account_name, "foo")

    def test_is_modified(self):
        """
        Test that we can determine when something has been modified.
        """
        self.controller.load()
        self.assertFalse(self.controller.is_modified)
        self.controller.local_landscape_host = "bing.bang.a.bang"
        self.assertTrue(self.controller.is_modified)
        self.controller.revert()
        self.assertFalse(self.controller.is_modified)
        self.controller.account_name = "soldierBlue"
        self.assertTrue(self.controller.is_modified)
        self.controller.revert()
        self.assertFalse(self.controller.is_modified)
        self.controller.registration_password = "HesAnIndianCowboyInTheRodeo"
        self.assertTrue(self.controller.is_modified)

    def test_commit(self):
        """
        Test that we can write configuration settings back to the config file.
        """
        self.controller.load()
        self.assertEqual("", self.controller.local_landscape_host)
        self.controller.local_landscape_host = "landscape.localdomain"
        self.assertEqual("landscape.localdomain",
                         self.controller.local_landscape_host)
        self.controller.commit()
        self.assertEqual("landscape.localdomain",
                         self.controller.local_landscape_host)
        self.controller.local_landscape_host = "boo"
        self.controller.revert()
        self.assertEqual("landscape.localdomain",
                         self.controller.local_landscape_host)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class EmptyConfigControllerTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""
        self.default_data = {"management-type": "not",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""
                             }

        super(EmptyConfigControllerTest, self).setUp()
        landscape.ui.model.configuration.state.DEFAULT_DATA[COMPUTER_TITLE] \
            = "me.here.com"
        settings = FakeGSettings(data=self.default_data)
        uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy, uisettings=uisettings)
        self.controller = ConfigController(model)
        self.controller.load()

    def test_defaulting(self):
        """
        Test we set the correct values when loading a blank configuration.
        """
        self.controller.load()
        self.assertEqual("not", self.controller.management_type)
        self.assertEqual("", self.controller.hosted_account_name)
        self.assertEqual("", self.controller.hosted_password)
        self.assertEqual("landscape.canonical.com",
                         self.controller.hosted_landscape_host)
        self.assertEqual("standalone", self.controller.local_account_name)
        self.assertEqual("", self.controller.local_password)
        self.assertEqual("me.here.com", self.controller.computer_title)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message
