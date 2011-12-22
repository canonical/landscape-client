from landscape.tests.helpers import LandscapeTest
from landscape.ui.controller.configuration import ConfigController
from landscape.configuration import (
    LandscapeSetupConfiguration, LandscapeSetupScript)


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
        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSetupConfiguration(None)
        self.script = LandscapeSetupScript(self.config)

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
    
        
                         
        
