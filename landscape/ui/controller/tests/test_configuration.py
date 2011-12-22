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
