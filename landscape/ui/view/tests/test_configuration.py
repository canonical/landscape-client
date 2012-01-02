import sys

from gi.repository import Gtk

from landscape.tests.helpers import LandscapeTest
from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.view.configuration import LandscapeClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController


class ConfigurationViewTest(LandscapeTest):

    def setUp(self):
        super(ConfigurationViewTest, self).setUp()
        config = """
[client]
data_path = %s
http_proxy = http://proxy.localdomain:3192
tags = a_tag
url = https://landscape.canonical.com/message-system
account_name = foo
registration_password = bar
computer_title = baz
https_proxy = https://proxy.localdomain:6192
ping_url = http://landscape.canonical.com/ping
""" % sys.path[0]
        self.config_filename = self.makeFile(config)
        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSetupConfiguration(None)

    def test_init(self):
        """
        Test that we correctly initialise the L{ConfigurationView} correctly
        from the controller.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        content_area = dialog.get_content_area()
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertTrue(dialog._hosted_radiobutton.get_active())
        self.assertFalse(dialog._dedicated_radiobutton.get_active())
        self.assertTrue(dialog._account_entry.get_sensitive())
        self.assertTrue(dialog._password_entry.get_sensitive())
        self.assertFalse(dialog._server_host_name_entry.get_sensitive())


    def test_toggle_radio_button(self):
        """
        Test that we disable and enable the correct entries when we toggle the
        dialog radiobuttons.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        self.assertTrue(dialog._hosted_radiobutton.get_active())
        self.assertFalse(dialog._dedicated_radiobutton.get_active())
        self.assertTrue(dialog._account_entry.get_sensitive())
        self.assertTrue(dialog._password_entry.get_sensitive())
        self.assertFalse(dialog._server_host_name_entry.get_sensitive())
        dialog._dedicated_radiobutton.set_active(True)
        self.assertFalse(dialog._hosted_radiobutton.get_active())
        self.assertTrue(dialog._dedicated_radiobutton.get_active())
        self.assertFalse(dialog._account_entry.get_sensitive())
        self.assertFalse(dialog._password_entry.get_sensitive())
        self.assertTrue(dialog._server_host_name_entry.get_sensitive())
        dialog._hosted_radiobutton.set_active(True)
        self.assertTrue(dialog._hosted_radiobutton.get_active())
        self.assertFalse(dialog._dedicated_radiobutton.get_active())
        self.assertTrue(dialog._account_entry.get_sensitive())
        self.assertTrue(dialog._password_entry.get_sensitive())
        self.assertFalse(dialog._server_host_name_entry.get_sensitive())

    def test_load_data_from_config(self):
        """
        Test that we load data into the appropriate entries from the
        configuration file.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        self.assertEqual(dialog._account_entry.get_text(), "foo")
        self.assertEqual(dialog._password_entry.get_text(), "bar")
        self.assertEqual(dialog._server_host_name_entry.get_text(), "")



class DedicatedConfigurationViewTest(LandscapeTest):

    def setUp(self):
        super(DedicatedConfigurationViewTest, self).setUp()
        config = """
[client]
data_path = %s
url = https://landscape.localdomain/message-system
computer_title = baz
ping_url = http://landscape.localdomain/ping
""" % sys.path[0]
        self.config_filename = self.makeFile(config)
        class MyLandscapeSetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]
        self.config = MyLandscapeSetupConfiguration(None)

    def test_init(self):
        """
        Test that we correctly initialise the L{ConfigurationView} correctly
        from the controller.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        content_area = dialog.get_content_area()
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertFalse(dialog._hosted_radiobutton.get_active())
        self.assertTrue(dialog._dedicated_radiobutton.get_active())
        self.assertFalse(dialog._account_entry.get_sensitive())
        self.assertFalse(dialog._password_entry.get_sensitive())
        self.assertTrue(dialog._server_host_name_entry.get_sensitive())

    def test_load_data_from_config(self):
        """
        Test that we load data into the appropriate entries from the
        configuration file.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        self.assertEqual(dialog._account_entry.get_text(), "")
        self.assertEqual(dialog._password_entry.get_text(), "")
        self.assertEqual(dialog._server_host_name_entry.get_text(), 
                         "landscape.localdomain")
