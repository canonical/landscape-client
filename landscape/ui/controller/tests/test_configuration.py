from landscape.tests.helpers import LandscapeTest
from landscape.ui.controller.configuration import (
    ConfigController, ConfigControllerLockError)
from landscape.ui.model.configuration import (
    LandscapeSettingsConfiguration)


class ConfigControllerTest(LandscapeTest):
    
    def setUp(self):
        super(ConfigControllerTest, self).setUp()
        config = """
[client]
data_path = /var/lib/landscape/client
http_proxy = http://proxy.localdomain:3192
tags = a_tag
url = https://landscape.canonical.com/message-system
account_name = foo
registration_password = bar
computer_title = baz
https_proxy = https://proxy.localdomain:6192
ping_url = http://landscape.canonical.com/ping

"""
        self.config_filename = self.makeFile(config)
        class MyLandscapeSettingsConfiguration(LandscapeSettingsConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSettingsConfiguration(None)

    def test_init(self):
        """
        Test that when we create a controller it has initial state read in
        directly from the configuration file.
        """
        controller = ConfigController(self.config)
        self.assertEqual(controller.data_path, "/var/lib/landscape/client")
        self.assertEqual(controller.http_proxy, "http://proxy.localdomain:3192")
        self.assertEqual(controller.tags, "a_tag")
        self.assertEqual(controller.url, 
                         "https://landscape.canonical.com/message-system")
        self.assertEqual(controller.account_name, "foo")
        self.assertEqual(controller.registration_password, "bar")
        self.assertEqual(controller.computer_title, "baz")
        self.assertEqual(controller.https_proxy,
                         "https://proxy.localdomain:6192")
        self.assertEqual(controller.ping_url, 
                         "http://landscape.canonical.com/ping")
        self.assertEqual(controller.server_host_name, "landscape.canonical.com")

    def test_set_server_hostname(self):
        """
        Test we can set the server_hostname correctly, and derive L{url} and
        L{ping_url} from it.
        """
        controller = ConfigController(self.config)
        self.assertEqual(controller.url, 
                         "https://landscape.canonical.com/message-system")
        self.assertEqual(controller.ping_url,
                         "http://landscape.canonical.com/ping")
        self.assertEqual(controller.server_host_name, 
                         "landscape.canonical.com")
        new_server_host_name = "landscape.localdomain"
        controller.server_host_name = new_server_host_name
        self.assertEqual(controller.server_host_name, new_server_host_name)
        self.assertEqual(controller.url,
                         "https://landscape.localdomain/message-system")
        self.assertEqual(controller.ping_url,
                         "http://landscape.localdomain/ping")

    def test_setting_server_host_name_also_sets_hosted(self):
        """
        Test that when we set the L{server_host_name} the L{hosted} value is
        also derived.
        """
        controller = ConfigController(self.config)
        self.assertTrue(controller.hosted)
        controller.server_host_name = "landscape.localdomain"
        self.assertFalse(controller.hosted)
        controller.server_host_name = "landscape.canonical.com"
        self.assertTrue(controller.hosted)


    def test_set_account_name(self):
        """
        Test that we can set the L{account_name} property.
        """
        controller = ConfigController(self.config)
        self.assertEqual(controller.account_name, "foo")
        controller.account_name = "shoe"
        self.assertEqual(controller.account_name, "shoe")

    def test_set_registration_password(self):
        """
        Test that we can set the L{registration_password} property.
        """
        controller = ConfigController(self.config)
        self.assertEquals(controller.registration_password, "bar")
        controller.registration_password = "nucker"
        self.assertEquals(controller.registration_password, "nucker")
        
    def test_revert(self):
        """
        Test that we can revert the controller to it's initial state.
        """
        controller = ConfigController(self.config)
        self.assertEqual(controller.server_host_name, "landscape.canonical.com")
        controller.server_host_name = "landscape.localdomain"
        self.assertEqual(controller.server_host_name, "landscape.localdomain")
        controller.revert()
        self.assertEqual(controller.server_host_name, "landscape.canonical.com")

    def test_is_modified(self):
        """
        Test that we can determine when something has been modified.
        """
        controller = ConfigController(self.config)
        self.assertFalse(controller.is_modified)
        controller.server_host_name = "bing.bang.a.bang"
        self.assertTrue(controller.is_modified)
        controller.revert()
        self.assertFalse(controller.is_modified)
        controller.account_name = "soldierBlue"
        self.assertTrue(controller.is_modified)
        controller.revert()
        self.assertFalse(controller.is_modified)
        controller.registration_password = "HesAnIndianCowboyInTheRodeo"
        self.assertTrue(controller.is_modified)
            
    def test_commit(self):
        """
        Test that we can write configuration settings back to the config file.
        """
        controller = ConfigController(self.config)
        self.assertEqual(controller.server_host_name, "landscape.canonical.com")
        controller.server_host_name = "landscape.localdomain"
        self.assertEqual(controller.server_host_name, "landscape.localdomain")
        controller.commit()
        self.assertEqual(controller.server_host_name, "landscape.localdomain")
        controller.revert()
        self.assertEqual(controller.server_host_name, "landscape.localdomain")

    def test_lock(self):
        """
        Test that we can lock out updates.
        """
        controller = ConfigController(self.config)
        controller.lock()
        self.assertRaises(ConfigControllerLockError, setattr, controller,
                          "server_host_name", "faily.fail.com")
        self.assertFalse(controller.is_modified)
        controller.unlock()
        controller.server_host_name = "successy.success.org"
        self.assertTrue(controller.is_modified)

        controller.revert()
        self.assertFalse(controller.is_modified)

        controller.lock()
        self.assertRaises(ConfigControllerLockError,
                          setattr,
                          controller,
                          "account_name",
                          "Failbert")
        self.assertFalse(controller.is_modified)
        controller.unlock()
        self.assertFalse(controller.is_modified)
        controller.account_name = "Winbob"
        self.assertTrue(controller.is_modified)

        controller.revert()
        self.assertFalse(controller.is_modified)

        controller.lock()
        self.assertRaises(ConfigControllerLockError,
                          setattr,
                          controller,
                          "registration_password",
                          "I Fail")
        self.assertFalse(controller.is_modified)
        controller.unlock()
        self.assertFalse(controller.is_modified)
        controller.registration_password = "I Win"
        self.assertTrue(controller.is_modified)



class EmptyConfigControllerTest(LandscapeTest):
    
    def setUp(self):
        super(EmptyConfigControllerTest, self).setUp()
        config = ""
        self.config_filename = self.makeFile(config)
        class MyLandscapeSettingsConfiguration(LandscapeSettingsConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSettingsConfiguration(None)

    def test_defaulting(self):
        """
        Test we set the correct values when switching between hosted and
        dedicated.
        """
        controller = ConfigController(self.config)
