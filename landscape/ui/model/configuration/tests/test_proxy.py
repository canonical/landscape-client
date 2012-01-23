import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.mechanism import (
    ConfigurationMechanism, INTERFACE_NAME)
from landscape.ui.model.configuration.proxy import ConfigurationProxy
from landscape.configuration import LandscapeSetupConfiguration


class ConfigurationProxyBaseTest(LandscapeTest):
    """
    L{ConfigurationProxyBaseTest} is a specialisation of L{LandscapeTest} that
    allows testing of the L{ConfigurationProxy} interface without invoking DBus
    calls.
    """

    def setUp(self, config):
        super(ConfigurationProxyBaseTest, self).setUp()
        self.config_filename = self.makeFile(config)

        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]

        self.config = MyLandscapeSetupConfiguration()

        # We have to do these steps because the ConfigurationMechanism inherits
        # from dbus.service.Object which throws a fit it notices you using it
        # without a mainloop.
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
        self.mechanism = ConfigurationMechanism(self.config, bus_name)

        def setup_interface(this, bus):
            # This just allows us to test without actually relying on dbus.
            this._interface = self.mechanism

        ConfigurationProxy._setup_interface = setup_interface
        self.proxy = ConfigurationProxy()
        self.proxy.load(["-c", self.config_filename])

    def tearDown(self):
        self.mechanism.remove_from_connection()
        super(ConfigurationProxyBaseTest, self).tearDown()


class ConfigurationProxyInterfaceTest(ConfigurationProxyBaseTest):
    """
    Test that we define the correct interface to a
    L{LandscapeSetupConfiguration} by really using one as the interface.
    """

    def setUp(self):
        super(ConfigurationProxyInterfaceTest, self).setUp(
            "[client]\n"
            "data_path = /var/lib/landscape/client/\n"
            "http_proxy = http://proxy.localdomain:3192\n"
            "tags = a_tag\n"
            "url = https://landscape.canonical.com/message-system\n"
            "account_name = foo\n"
            "registration_password = boink\n"
            "computer_title = baz\n"
            "https_proxy = https://proxy.localdomain:6192\n"
            "ping_url = http://landscape.canonical.com/ping\n")

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
        Test that we can get and set and account name via the configuration
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
