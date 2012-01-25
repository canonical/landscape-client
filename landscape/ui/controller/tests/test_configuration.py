from landscape.ui.controller.configuration import (
    ConfigController, ConfigControllerLockError)
from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, dbus_test_should_skip, dbus_skip_message)
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

        super(ConfigControllerTest, self).setUp()

        self.controller = ConfigController(self.proxy)

        def get_fqdn():
            return "me.here.com"

        self.controller.getfqdn = get_fqdn
        self.controller.load()

    def test_init(self):
        """
        Test that when we create a controller it has initial state read in
        directly from the configuration file.
        """
        self.controller.load()
        self.assertEqual(self.controller.data_path,
                         "/var/lib/landscape/client/")
        self.assertEqual(self.controller.http_proxy,
                         "http://proxy.localdomain:3192")
        self.assertEqual(self.controller.tags, "a_tag")
        self.assertEqual(self.controller.url,
                         "https://landscape.canonical.com/message-system")
        self.assertEqual(self.controller.account_name, "foo")
        self.assertEqual(self.controller.registration_password, "bar")
        self.assertEqual(self.controller.computer_title, "baz")
        self.assertEqual(self.controller.https_proxy,
                         "https://proxy.localdomain:6192")
        self.assertEqual(self.controller.ping_url,
                         "http://landscape.canonical.com/ping")
        self.assertEqual(self.controller.server_host_name,
                         "landscape.canonical.com")

    def test_set_server_hostname(self):
        """
        Test we can set the server_hostname correctly, and derive L{url} and
        L{ping_url} from it.
        """
        self.controller.load()
        self.assertEqual(self.controller.url,
                         "https://landscape.canonical.com/message-system")
        self.assertEqual(self.controller.ping_url,
                         "http://landscape.canonical.com/ping")
        self.assertEqual(self.controller.server_host_name,
                         "landscape.canonical.com")
        new_server_host_name = "landscape.localdomain"
        self.controller.server_host_name = new_server_host_name
        self.assertEqual(self.controller.server_host_name,
                         new_server_host_name)
        self.assertEqual(self.controller.url,
                         "https://landscape.localdomain/message-system")
        self.assertEqual(self.controller.ping_url,
                         "http://landscape.localdomain/ping")

    def test_setting_server_host_name_also_sets_hosted(self):
        """
        Test that when we set the L{server_host_name} the L{hosted} value is
        also derived.
        """
        self.controller.load()
        self.assertTrue(self.controller.hosted)
        self.controller.server_host_name = "landscape.localdomain"
        self.assertFalse(self.controller.hosted)
        self.controller.server_host_name = "landscape.canonical.com"
        self.assertTrue(self.controller.hosted)

    def test_set_account_name(self):
        """
        Test that we can set the L{account_name} property.
        """
        self.controller.load()
        self.assertEqual(self.controller.account_name, "foo")
        self.controller.account_name = "shoe"
        self.assertEqual(self.controller.account_name, "shoe")

    def test_set_registration_password(self):
        """
        Test that we can set the L{registration_password} property.
        """
        self.controller.load()
        self.assertEquals(self.controller.registration_password, "bar")
        self.controller.registration_password = "nucker"
        self.assertEquals(self.controller.registration_password, "nucker")

    def test_revert(self):
        """
        Test that we can revert the controller to it's initial state.
        """
        self.controller.load()
        self.assertEqual(self.controller.server_host_name,
                         "landscape.canonical.com")
        self.controller.server_host_name = "landscape.localdomain"
        self.assertEqual(self.controller.server_host_name,
                         "landscape.localdomain")
        self.controller.revert()
        self.assertEqual(self.controller.server_host_name,
                         "landscape.canonical.com")

    def test_is_modified(self):
        """
        Test that we can determine when something has been modified.
        """
        self.controller.load()
        self.assertFalse(self.controller.is_modified)
        self.controller.server_host_name = "bing.bang.a.bang"
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
        self.assertEqual(self.controller.server_host_name,
                         "landscape.canonical.com")
        self.controller.server_host_name = "landscape.localdomain"
        self.assertEqual(self.controller.server_host_name,
                         "landscape.localdomain")
        self.controller.commit()
        self.assertEqual(self.controller.server_host_name,
                         "landscape.localdomain")
        self.controller.revert()
        self.assertEqual(self.controller.server_host_name,
                         "landscape.localdomain")

    def test_lock(self):
        """
        Test that we can lock out updates.
        """
        self.controller.load()
        self.controller.lock()
        self.assertRaises(ConfigControllerLockError, setattr, self.controller,
                          "server_host_name", "faily.fail.com")
        self.assertFalse(self.controller.is_modified)
        self.controller.unlock()
        self.controller.server_host_name = "successy.success.org"
        self.assertTrue(self.controller.is_modified)

        self.controller.revert()
        self.assertFalse(self.controller.is_modified)

        self.controller.lock()
        self.assertRaises(ConfigControllerLockError,
                          setattr,
                          self.controller,
                          "account_name",
                          "Failbert")
        self.assertFalse(self.controller.is_modified)
        self.controller.unlock()
        self.assertFalse(self.controller.is_modified)
        self.controller.account_name = "Winbob"
        self.assertTrue(self.controller.is_modified)

        self.controller.revert()
        self.assertFalse(self.controller.is_modified)

        self.controller.lock()
        self.assertRaises(ConfigControllerLockError,
                          setattr,
                          self.controller,
                          "registration_password",
                          "I Fail")
        self.assertFalse(self.controller.is_modified)
        self.controller.unlock()
        self.assertFalse(self.controller.is_modified)
        self.controller.registration_password = "I Win"
        self.assertTrue(self.controller.is_modified)

    if dbus_test_should_skip:
        test_lock.skip = dbus_skip_message
        test_commit.skip = dbus_skip_message
        test_is_modified = dbus_skip_message
        test_revert = dbus_skip_message
        test_set_registration_password = dbus_skip_message
        test_set_account_name = dbus_skip_message
        test_setting_server_host_name_also_sets_hosted = dbus_skip_message
        test_set_server_hostname = dbus_skip_message
        test_init = dbus_skip_message


class EmptyConfigControllerTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""
        super(EmptyConfigControllerTest, self).setUp()

        self.controller = ConfigController(self.proxy)

        def get_fqdn():
            return "me.here.com"

        self.controller.getfqdn = get_fqdn
        self.controller.load()

    def test_defaulting(self):
        """
        Test we set the correct values when switching between hosted and
        dedicated.
        """
        self.controller.load()
        self.assertEqual(None, self.controller.account_name)
        self.assertEqual(None, self.controller.registration_password)
        self.assertEqual("landscape.canonical.com",
                         self.controller.server_host_name)
        self.controller.account_name = "Bungle"
        self.controller.default_dedicated()
        self.assertEqual("standalone", self.controller.account_name)
        self.assertEqual(None, self.controller.registration_password)
        self.assertEqual("landscape.localdomain",
                         self.controller.server_host_name)
        self.controller.default_hosted()
        self.assertEqual(None, self.controller.account_name)
        self.assertEqual(None, self.controller.registration_password)
        self.assertEqual("landscape.canonical.com",
                         self.controller.server_host_name)
        self.controller.default_dedicated()
        self.controller.server_host_name = "test.machine"
        self.controller.default_dedicated()
        self.assertEqual("test.machine", self.controller.server_host_name)
        self.controller.default_hosted()
        self.assertEqual("landscape.canonical.com",
                         self.controller.server_host_name)
        self.controller.default_dedicated()
        self.assertEqual("test.machine", self.controller.server_host_name)

    def test_default_computer_title(self):
        """
        Test we set the computer title to host name when it isn't already set
        in the config file.
        """
        self.assertEqual("me.here.com", self.controller.computer_title)

    if dbus_test_should_skip:
        test_default_computer_title.skip = dbus_skip_message
        test_defaulting.skip = dbus_skip_message
