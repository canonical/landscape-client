import os
import subprocess
import time

import dbus

from landscape.configuration import LandscapeSetupConfiguration
from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.mechanism import (
    ConfigurationMechanism, INTERFACE_NAME, OBJECT_PATH)


class MechanismWithoutPolicyTestCase(LandscapeTest):
    """
    This class contains DBus calls to test that in the absence of a PolicyKit
    policy declaration calls are refused (even when run on the session bus with
    the same user).
    """

    def setUp(self):
        super(MechanismWithoutPolicyTestCase, self).setUp()
        self._exerciser_file = os.path.join(os.path.dirname(__file__),
                                            'mechanism_exerciser.py')
        env = os.environ.copy()
        self.p = subprocess.Popen(["dbus-launch",
                                   "--exit-with-session",
                                   self._exerciser_file], env=env)
        # Wait for the service to become available
        time.sleep(1)

    def test_accessing_interface_fails(self):
        """
        Test that accessing fails outside of a secure context.
        """
        bus = dbus.SessionBus()
        service = bus.get_object(INTERFACE_NAME, OBJECT_PATH)
        get_account_name = service.get_dbus_method(
            'get_account_name', INTERFACE_NAME)
        set_account_name = service.get_dbus_method(
            'set_account_name', INTERFACE_NAME)
        get_computer_title = service.get_dbus_method(
            'get_computer_title', INTERFACE_NAME)
        set_computer_title = service.get_dbus_method(
            'set_computer_title', INTERFACE_NAME)
        get_data_path = service.get_dbus_method(
            'get_data_path', INTERFACE_NAME)
        set_data_path = service.get_dbus_method(
            'set_data_path', INTERFACE_NAME)
        get_http_proxy = service.get_dbus_method(
            'get_http_proxy', INTERFACE_NAME)
        set_http_proxy = service.get_dbus_method(
            'set_http_proxy', INTERFACE_NAME)
        get_https_proxy = service.get_dbus_method(
            'get_https_proxy', INTERFACE_NAME)
        set_https_proxy = service.get_dbus_method(
            'set_https_proxy', INTERFACE_NAME)
        get_ping_url = service.get_dbus_method(
            'get_ping_url', INTERFACE_NAME)
        set_ping_url = service.get_dbus_method(
            'set_ping_url', INTERFACE_NAME)
        get_registration_password = service.get_dbus_method(
            'get_registration_password', INTERFACE_NAME)
        set_registration_password = service.get_dbus_method(
            'set_registration_password', INTERFACE_NAME)
        get_tags = service.get_dbus_method(
            'get_tags', INTERFACE_NAME)
        set_tags = service.get_dbus_method(
            'set_tags', INTERFACE_NAME)
        get_url = service.get_dbus_method(
            'get_url', INTERFACE_NAME)
        set_url = service.get_dbus_method(
            'set_url', INTERFACE_NAME)
        self.assertRaises(dbus.DBusException, get_account_name)
        self.assertRaises(dbus.DBusException, set_account_name, "foo")
        self.assertRaises(dbus.DBusException, get_computer_title)
        self.assertRaises(dbus.DBusException, set_computer_title, "foo")
        self.assertRaises(dbus.DBusException, get_data_path)
        self.assertRaises(dbus.DBusException, set_data_path, "foo")
        self.assertRaises(dbus.DBusException, get_http_proxy)
        self.assertRaises(dbus.DBusException, set_http_proxy, "foo")
        self.assertRaises(dbus.DBusException, get_https_proxy)
        self.assertRaises(dbus.DBusException, set_https_proxy, "foo")
        self.assertRaises(dbus.DBusException, get_ping_url)
        self.assertRaises(dbus.DBusException, set_ping_url, "foo")
        self.assertRaises(dbus.DBusException, get_registration_password)
        self.assertRaises(dbus.DBusException, set_registration_password, "foo")
        self.assertRaises(dbus.DBusException, get_tags)
        self.assertRaises(dbus.DBusException, set_tags, "foo")
        self.assertRaises(dbus.DBusException, get_url)
        self.assertRaises(dbus.DBusException, set_url, "foo")

    def tearDown(self):
        os.kill(self.p.pid, 15)


class MechanismTest(LandscapeTest):
    """
    Test that we can use mechanism calls successfully from within a secure
    context (the easiest to achieve is in-process calls.
    """

    def setUp(self):
        super(MechanismTest, self).setUp()
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
        self.assertEqual(self.mechanism.get_account_name(), "foo")

    def test_set_account_name(self):
        self.mechanism.set_account_name("bar")
        self.assertEqual(self.mechanism.get_account_name(), "bar")

    def test_get_data_path(self):
        self.assertEqual(self.mechanism.get_data_path(),
                         "/var/lib/landscape/client/")

    def set_data_path(self):
        self.mechanism.set_data_path("bar")
        self.assertEqual(self.mechanism.get_data_path(),
                         "bar")

    def test_get_http_proxy(self):
        self.assertEqual(self.mechanism.get_http_proxy(),
                         "http://proxy.localdomain:3192")

    def test_set_http_proxy(self):
        self.mechanism.set_http_proxy("bar")
        self.assertEqual(self.mechanism.get_http_proxy(),
                         "bar")

    def test_get_tags(self):
        self.assertEquals(self.mechanism.get_tags(),
                          "a_tag")

    def test_set_tags(self):
        self.mechanism.set_tags("bar")
        self.assertEquals(self.mechanism.get_tags(),
                          "bar")

    def test_get_url(self):
        self.assertEquals(self.mechanism.get_url(),
                          "https://landscape.canonical.com/message-system")

    def test_set_url(self):
        self.mechanism.set_url("bar")
        self.assertEquals(self.mechanism.get_url(),
                          "bar")

    def test_get_ping_url(self):
        self.assertEquals(self.mechanism.get_ping_url(),
                          "http://landscape.canonical.com/ping")

    def test_set_ping_url(self):
        self.mechanism.set_ping_url("bar")
        self.assertEquals(self.mechanism.get_ping_url(),
                          "bar")

    def test_get_registration_password(self):
        self.assertEquals(self.mechanism.get_registration_password(),
                          "boink")

    def test_set_registration_password(self):
        self.mechanism.set_registration_password("bar")
        self.assertEquals(self.mechanism.get_registration_password(),
                          "bar")

    def test_get_computer_title(self):
        self.assertEquals(self.mechanism.get_computer_title(),
                          "baz")

    def test_set_computer_title(self):
        self.mechanism.set_computer_title("bar")
        self.assertEquals(self.mechanism.get_computer_title(),
                          "bar")

    def test_get_https_proxy(self):
        self.assertEqual(self.mechanism.get_https_proxy(),
                         "https://proxy.localdomain:6192")

    def test_set_https_proxy(self):
        self.mechanism.set_https_proxy("bar")
        self.assertEqual(self.mechanism.get_https_proxy(),
                         "bar")
