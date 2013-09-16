from landscape.configuration import LandscapeSetupConfiguration
from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import (
    dbus_test_should_skip, dbus_skip_message)
if not dbus_test_should_skip:
    import dbus
    from landscape.ui.model.configuration.mechanism import (
        ConfigurationMechanism, INTERFACE_NAME)


class MechanismTest(LandscapeTest):
    """
    Test that we can use mechanism calls successfully from within a secure
    context (the easiest to achieve is in-process calls.
    """

    def setUp(self):
        super(MechanismTest, self).setUp()
        config = "[client]\n"
        config += "data_path = /var/lib/landscape/client/\n"
        config += "http_proxy = http://proxy.localdomain:3192\n"
        config += "tags = a_tag\n"
        config += "url = https://landscape.canonical.com/message-system\n"
        config += "account_name = foo\n"
        config += "registration_key = boink\n"
        config += "computer_title = baz\n"
        config += "https_proxy = https://proxy.localdomain:6192\n"
        config += "ping_url = http://landscape.canonical.com/ping\n"
        self.config_filename = self.makeFile(config)
        self.config = LandscapeSetupConfiguration()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SessionBus(private=True)
        bus_name = dbus.service.BusName(INTERFACE_NAME, bus)
        self.mechanism = ConfigurationMechanism(self.config, bus_name)
        self.config.load(["-c", self.config_filename])

    def tearDown(self):
        self.mechanism.remove_from_connection()
        super(MechanismTest, self).tearDown()

    def test_is_local_call(self):
        """
        Test simple mechanism for checking if a call is local does the right
        thing.  Anything passed to this function that is not L{None} will
        result in is returning False - this in turn means that bypassing
        security will not happen, which is the right thing in failure cases
        too.
        """
        self.assertTrue(self.mechanism._is_local_call(None, None))
        self.assertFalse(self.mechanism._is_local_call(True, True))

    def test_get_account_name(self):
        """
        Test we can get account name from the mechanism.
        """
        self.assertEqual("foo", self.mechanism.get("account_name"))

    def test_set_account_name(self):
        """
        Test we can set the account name via the mechanism.
        """
        self.mechanism.set("account_name", "bar")
        self.assertEqual("bar", self.mechanism.get("account_name"))

    def test_set_account_name_unicode(self):
        """
        Non-ascii characters are replaced before passing to underlying config.
        """
        self.mechanism.set("account_name", u"unicode\u00a3unicode")
        self.assertEqual("unicode?unicode", self.mechanism.get("account_name"))

    def test_no_unicode_to_underlying_config(self):
        """
        Non-ascii characters are replaced before passing to underlying config.
        """
        class FakeConfig(object):
            def __init__(self):
                self.account_name = None

        fake_config = FakeConfig()
        self.mechanism._config = fake_config
        self.mechanism.set("account_name", u"unicode\u00a3unicode")
        self.assertEqual("unicode?unicode", fake_config.account_name)

    def test_get_data_path(self):
        """
        Test we can get the data path from the mechanism.
        """
        self.assertEqual("/var/lib/landscape/client/",
                         self.mechanism.get("data_path"))

    def set_data_path(self):
        """
        Test we can set the data path via the mechanism.
        """
        self.mechanism.set("data_path", "bar")
        self.assertEqual("bar", self.mechanism.get("data_path"))

    def test_get_http_proxy(self):
        """
        Test that we can get the HTTP proxy from the mechanism.
        """
        self.assertEqual("http://proxy.localdomain:3192",
                         self.mechanism.get("http_proxy"))

    def test_set_http_proxy(self):
        """
        Test that we can set the HTTP proxy via the mechanism.
        """
        self.mechanism.set("http_proxy", "bar")
        self.assertEqual("bar", self.mechanism.get("http_proxy"))

    def test_get_tags(self):
        """
        Test that we can get Tags from the mechanism.
        """
        self.assertEqual("a_tag", self.mechanism.get("tags"))

    def test_set_tags(self):
        """
        Test that we can set Tags via the mechanism.
        """
        self.mechanism.set("tags", "bar")
        self.assertEqual("bar", self.mechanism.get("tags"))

    def test_get_url(self):
        """
        Test that we can get URL from the mechanism.
        """
        self.assertEqual("https://landscape.canonical.com/message-system",
                          self.mechanism.get("url"))

    def test_set_url(self):
        """
        Test that we can set the URL via the mechanisms.
        """
        self.mechanism.set("url", "bar")
        self.assertEqual(self.mechanism.get("url"), "bar")

    def test_get_ping_url(self):
        """
        Test that we can get the Ping URL from the mechanism.
        """
        self.assertEqual("http://landscape.canonical.com/ping",
                          self.mechanism.get("ping_url"))

    def test_set_ping_url(self):
        """
        Test that we can set the Ping URL via the mechanism.
        """
        self.mechanism.set("ping_url", "bar")
        self.assertEqual("bar", self.mechanism.get("ping_url"))

    def test_get_registration_key(self):
        """
        Test that we can get the registration key from the mechanism.
        """
        self.assertEqual("boink", self.mechanism.get("registration_key"))

    def test_set_registration_key(self):
        """
        Test that we can set the registration key via the mechanism.
        """
        self.mechanism.set("registration_key", "bar")
        self.assertEqual("bar", self.mechanism.get("registration_key"))

    def test_get_computer_title(self):
        """
        Test that we can get the computer title from the mechanism.
        """
        self.assertEqual("baz", self.mechanism.get("computer_title"))

    def test_set_computer_title(self):
        """
        Test that we can set the computer title via the mechanism.
        """
        self.mechanism.set("computer_title", "bar")
        self.assertEqual("bar", self.mechanism.get("computer_title"))

    def test_get_https_proxy(self):
        """
        Test that we can get the HTTPS Proxy from the mechanism.
        """
        self.assertEqual("https://proxy.localdomain:6192",
                         self.mechanism.get("https_proxy"))

    def test_set_https_proxy(self):
        """
        Test that we can set the HTTPS Proxy via the mechanism.
        """
        self.mechanism.set("https_proxy", "bar")
        self.assertEqual("bar", self.mechanism.get("https_proxy"))

    def test_exit(self):
        """
        Test that we cause the mechanism to exit.
        """
        self.assertRaises(SystemExit, self.mechanism.exit)

    if dbus_test_should_skip:
        skip = dbus_skip_message
