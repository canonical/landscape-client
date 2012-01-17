import dbus

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.mechanism import (
    ConfigurationMechanism, INTERFACE_NAME)
from landscape.ui.model.configuration.proxy import ConfigurationProxy
from landscape.configuration import LandscapeSetupConfiguration


class ConfigurationProxyInterfaceTest(LandscapeTest):
    """ 
    Test that we define the correct interface to a
    L{LandscapeSetupConfiguration} by really using one as the interface.
    """

    def setUp(self):
        super(ConfigurationProxyInterfaceTest, self).setUp()
        config = "[client]"
        config += "data_path = /var/lib/landscape/client\n"
        config += "http_proxy = http://proxy.localdomain:3192\n"
        config += "tags = a_tag\n"
        config += "url = https://landscape.canonical.com/message-system\n"
        config += "account_name = foo\n"
        config += "registration_password = boink\n"
        config += "computer_title = baz\n"
        config += "https_proxy = https://proxy.localdomain:6192\n"
        config += "ping_url = http://landscape.canonical.com/ping\n"
        self.config_filename = self.makeFile(config)

        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]

        self.config = MyLandscapeSetupConfiguration()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus()
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
        self.mechanism = ConfigurationMechanism(self.config, bus_name)

        def setup_interface(this, bus):
            """
            This just allows us to test without actually relying on dbus.
            """
            this._iface = self.mechanism
        
        ConfigurationProxy._setup_iface = setup_interface
        self.proxy = ConfigurationProxy()
        self.proxy.load(["-c", self.config_filename])
    
    def tearDown(self):
        self.mechanism.remove_from_connection()
        super(ConfigurationProxyInterfaceTest, self).tearDown()    

    def test_account_name(self):
        self.assertEqual(self.proxy.account_name, "foo")
        self.proxy.account_name = "bar"
        self.assertEqual(self.proxy.account_name, "bar")

    def test_computer_title(self):
        self.assertEqual(self.proxy.computer_title, "baz")
        self.proxy.computer_title = "bar"
        self.assertEqual(self.proxy.computer_title, "bar")

    def test_data_path(self):
        self.assertEqual(self.proxy.data_path, "/var/lib/landscape/client/")
        self.proxy.data_path = "bar"
        self.assertEqual(self.proxy.data_path, "bar")

    def test_http_proxy(self):
        self.assertEqual(self.proxy.http_proxy, 
                         "http://proxy.localdomain:3192")
        self.proxy.http_proxy = "bar"
        self.assertEqual(self.proxy.http_proxy, "bar")

    def test_https_proxy(self):
        self.assertEqual(self.proxy.https_proxy,
                         "https://proxy.localdomain:6192")
        self.proxy.https_proxy = "bar"
        self.assertEqual(self.proxy.https_proxy, "bar")

    def test_ping_url(self):
        self.assertEqual(self.proxy.ping_url,
                         "http://landscape.canonical.com/ping")
        self.proxy.ping_url = "bar"
        self.assertEqual(self.proxy.ping_url, "bar")

    def test_registration_password(self):
        self.assertEqual(self.proxy.registration_password, "boink")
        self.proxy.registration_password = "bar"
        self.assertEqual(self.proxy.registration_password, "bar")

    def test_tags(self):

        self.assertEqual(self.proxy.tags, "a_tag")
        self.proxy.tags = "bar"
        self.assertEqual(self.proxy.tags, "bar")

    def test_url(self):
        self.assertEqual(self.proxy.url,
                         "https://landscape.canonical.com/message-system")
        self.proxy.url = "bar"
        self.assertEqual(self.proxy.url, "bar")

