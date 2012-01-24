from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import ConfigurationProxyHelper
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
        self.assertEqual(self.proxy.account_name, "foo")
        self.proxy.account_name = "bar"
        self.assertEqual(self.proxy.account_name, "bar")

    def test_computer_title(self):
        """
        Test that we can get and set a computer title via the configuration
        proxy.
        """
        self.assertEqual(self.proxy.computer_title, "baz")
        self.proxy.computer_title = "bar"
        self.assertEqual(self.proxy.computer_title, "bar")

    def test_data_path(self):
        """
        Test that we can get and set the data path via the configuration proxy.
        """
        self.assertEqual(self.proxy.data_path, "/var/lib/landscape/client/")
        self.proxy.data_path = "bar"
        self.assertEqual(self.proxy.data_path, "bar")

    def test_http_proxy(self):
        """
        Test that we can get and set the HTTP proxy via the configuration
        proxy.
        """
        self.assertEqual(self.proxy.http_proxy,
                         "http://proxy.localdomain:3192")
        self.proxy.http_proxy = "bar"
        self.assertEqual(self.proxy.http_proxy, "bar")

    def test_https_proxy(self):
        """
        Test that we can get and set the HTTPS proxy via the configuration
        proxy.
        """
        self.assertEqual(self.proxy.https_proxy,
                         "https://proxy.localdomain:6192")
        self.proxy.https_proxy = "bar"
        self.assertEqual(self.proxy.https_proxy, "bar")

    def test_ping_url(self):
        """
        Test that we can get and set the ping URL via the configuration proxy.
        """
        self.assertEqual(self.proxy.ping_url,
                         "http://landscape.canonical.com/ping")
        self.proxy.ping_url = "bar"
        self.assertEqual(self.proxy.ping_url, "bar")

    def test_registration_password(self):
        """
        Test that we can get and set the registration password via the
        configuration proxy.
        """
        self.assertEqual(self.proxy.registration_password, "boink")
        self.proxy.registration_password = "bar"
        self.assertEqual(self.proxy.registration_password, "bar")

    def test_tags(self):
        """
        Test that we can get and set the tags via the configuration proxy.
        """
        self.assertEqual(self.proxy.tags, "a_tag")
        self.proxy.tags = "bar"
        self.assertEqual(self.proxy.tags, "bar")

    def test_url(self):
        """
        Test that we can get and set the URL via the configuration proxy.
        """
        self.assertEqual(self.proxy.url,
                         "https://landscape.canonical.com/message-system")
        self.proxy.url = "bar"
        self.assertEqual(self.proxy.url, "bar")
