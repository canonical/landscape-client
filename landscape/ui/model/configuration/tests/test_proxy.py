from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, dbus_test_should_skip, dbus_skip_message,
    got_gobject_introspection, gobject_skip_message)
if got_gobject_introspection:
    from landscape.ui.model.configuration.mechanism import (
        PermissionDeniedByPolicy)
if not dbus_test_should_skip:
    import dbus
from landscape.tests.helpers import LandscapeTest


class AuthenticationFailureTest(LandscapeTest):
    """
    Test that an authentication failure is handled correctly.
    """
    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.config_string = ""

        super(AuthenticationFailureTest, self).setUp()

    def test_failed_authentication(self):
        """
        Test that load returns False when authentication fails.
        """

        def fake_policy_failure_load(arglist):
            """
            This simulates what you see if you click "Cancel" or give the wrong
            credentials 3 times when L{PolicyKit} challenges you.
            """
            raise PermissionDeniedByPolicy()

        def fake_timeout_failure_load(arglist):
            """
            This simulates what you see if you take no action when L{PolicyKit}
            challenges you.
            """

            class FakeNoReply(dbus.DBusException):
                """
                Simulate a L{DBus} L{NoReply} exception.
                """
                _dbus_error_name = "org.freedesktop.DBus.Error.NoReply"

            raise FakeNoReply()

        self.mechanism.load = fake_policy_failure_load
        self.assertFalse(self.proxy.load([]))
        self.mechanism.load = fake_timeout_failure_load
        self.assertFalse(self.proxy.load([]))

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message


class ConfigurationProxyInterfaceTest(LandscapeTest):
    """
    Test that we define the correct interface to a
    L{LandscapeSetupConfiguration} by really using one as the interface.
    """

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

        super(ConfigurationProxyInterfaceTest, self).setUp()

    def test_method_docstrings(self):
        """
        Test that we pass through the docstrings for methods.
        """
        self.assertEqual(self.proxy.load.__doc__,
                         LandscapeSetupConfiguration.load.__doc__)
        self.assertEqual(self.proxy.reload.__doc__,
                         LandscapeSetupConfiguration.reload.__doc__)
        self.assertEqual(self.proxy.write.__doc__,
                         LandscapeSetupConfiguration.write.__doc__)

    def test_account_name(self):
        """
        Test that we can get and set an account name via the configuration
        proxy.
        """
        self.assertEqual("foo", self.proxy.account_name)
        self.proxy.account_name = "bar"
        self.assertEqual("bar", self.proxy.account_name)
        self.assertEqual("bar", self.config.account_name)

    def test_computer_title(self):
        """
        Test that we can get and set a computer title via the configuration
        proxy.
        """
        self.assertEqual("baz", self.proxy.computer_title)
        self.proxy.computer_title = "bar"
        self.assertEqual("bar", self.proxy.computer_title)
        self.assertEqual("bar", self.config.computer_title)

    def test_data_path(self):
        """
        Test that we can get and set the data path via the configuration proxy.
        """
        self.assertEqual("/var/lib/landscape/client/", self.proxy.data_path)
        self.proxy.data_path = "bar"
        self.assertEqual("bar", self.proxy.data_path)
        self.assertEqual("bar", self.config.data_path)

    def test_http_proxy(self):
        """
        Test that we can get and set the HTTP proxy via the configuration
        proxy.
        """
        self.assertEqual("http://proxy.localdomain:3192",
                         self.proxy.http_proxy)
        self.proxy.http_proxy = "bar"
        self.assertEqual("bar", self.proxy.http_proxy)
        self.assertEqual("bar", self.config.http_proxy)

    def test_https_proxy(self):
        """
        Test that we can get and set the HTTPS proxy via the configuration
        proxy.
        """
        self.assertEqual("https://proxy.localdomain:6192",
                         self.proxy.https_proxy)
        self.proxy.https_proxy = "bar"
        self.assertEqual("bar", self.proxy.https_proxy)
        self.assertEqual("bar", self.config.https_proxy)

    def test_ping_url(self):
        """
        Test that we can get and set the ping URL via the configuration proxy.
        """
        self.assertEqual("http://landscape.canonical.com/ping",
                         self.proxy.ping_url)
        self.proxy.ping_url = "bar"
        self.assertEqual("bar", self.proxy.ping_url)
        self.assertEqual("bar", self.config.ping_url)

    def test_registration_password(self):
        """
        Test that we can get and set the registration password via the
        configuration proxy.
        """
        self.assertEqual("boink", self.proxy.registration_password)
        self.proxy.registration_password = "bar"
        self.assertEqual("bar", self.proxy.registration_password)
        self.assertEqual("bar", self.config.registration_password)

    def test_tags(self):
        """
        Test that we can get and set the tags via the configuration proxy.
        """
        self.assertEqual("a_tag", self.proxy.tags)
        self.proxy.tags = "bar"
        self.assertEqual("bar", self.proxy.tags)
        self.assertEqual("bar", self.config.tags)

    def test_url(self):
        """
        Test that we can get and set the URL via the configuration proxy.
        """
        self.assertEqual("https://landscape.canonical.com/message-system",
                         self.proxy.url)
        self.proxy.url = "bar"
        self.assertEqual("bar", self.proxy.url)
        self.assertEqual("bar", self.config.url)

    def test_exit(self):
        """
        Test that we can cause the mechanism to exit.
        """
        self.assertRaises(SystemExit, self.proxy.exit, asynchronous=False)

    if not got_gobject_introspection:
        skip = gobject_skip_message
    elif dbus_test_should_skip:
        skip = dbus_skip_message
