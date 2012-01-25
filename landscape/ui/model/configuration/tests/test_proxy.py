from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, dbus_test_should_skip, dbus_skip_message)
from landscape.configuration import LandscapeSetupConfiguration


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

    if dbus_test_should_skip:
        test_url.skip = dbus_skip_message
        test_tags.skip = dbus_skip_message
        test_registration_password.skip = dbus_skip_message
        test_ping_url = dbus_skip_message
        test_https_proxy = dbus_skip_message
        test_http_proxy = dbus_skip_message
        test_data_path = dbus_skip_message
        test_computer_title = dbus_skip_message
        test_account_name = dbus_skip_message
