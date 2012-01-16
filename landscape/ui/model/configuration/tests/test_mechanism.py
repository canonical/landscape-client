import os
import subprocess
import threading
import time

import dbus
import gobject


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

    def test_get_account_name(self):
        """
        Test that L{get_account_name} fails outside of a secure context and
        succeeds within a secure context.
        """
        bus = dbus.SessionBus()
        helloservice = bus.get_object(INTERFACE_NAME, OBJECT_PATH)
        get_account_name = helloservice.get_dbus_method('get_account_name', 
                                             INTERFACE_NAME)
        self.assertRaises(dbus.DBusException, get_account_name)
        
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
        config += "registration_password = bar\n"
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

