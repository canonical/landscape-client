import sys

try:
    from gi.repository import Gtk
    got_gobject_introspection = True
except ImportError:
    got_gobject_introspection = False
    gobject_skip_message = "GObject Introspection module unavailable"

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
        self.assertEqual(dialog._server_host_name_entry.get_text(),
                         "landscape.canonical.com")

    def test_revert(self):
        """
        Test that we can revert the UI values using the controller.
        """
        controller = ConfigController(self.config)
        dialog = LandscapeClientSettingsDialog(controller)
        self.assertEqual(dialog._account_entry.get_text(), "foo")
        self.assertEqual(dialog._password_entry.get_text(), "bar")
        self.assertEqual(dialog._server_host_name_entry.get_text(),
                         "landscape.canonical.com")
        dialog._dedicated_radiobutton.set_active(True)
        dialog._server_host_name_entry.set_text("more.barn")
        self.assertEqual(dialog._account_entry.get_text(), "foo")
        self.assertEqual(dialog._password_entry.get_text(), "bar")
        self.assertEqual(dialog._server_host_name_entry.get_text(),
                         "more.barn")
        self.assertTrue(dialog._dedicated_radiobutton.get_active())
        self.assertFalse(dialog._hosted_radiobutton.get_active())
        dialog.revert(None)
        self.assertEqual(dialog._account_entry.get_text(), "foo")
        self.assertEqual(dialog._password_entry.get_text(), "bar")
        self.assertEqual(dialog._server_host_name_entry.get_text(),
                         "landscape.canonical.com")
        self.assertFalse(dialog._dedicated_radiobutton.get_active())
        self.assertTrue(dialog._hosted_radiobutton.get_active())

    if not got_gobject_introspection:
        test_revert.skip = gobject_skip_message
        test_load_data_from_config.skip = gobject_skip_message
        test_toggle_radio_button.skip = gobject_skip_message
        test_init.skip = gobject_skip_message


class ConfigurationViewCommitTest(LandscapeTest):

    def setUp(self):
        super(ConfigurationViewCommitTest, self).setUp()
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
        self.real_write_back = LandscapeClientSettingsDialog._write_back
        self.write_back_called = False

        def fake_write_back(obj):
            self.write_back_called = True
        LandscapeClientSettingsDialog._write_back = fake_write_back
        self.controller = ConfigController(self.config)
        self.dialog = LandscapeClientSettingsDialog(self.controller)

    def tearDown(self):
        self.controller = None
        self.dialog.destroy()
        self.dialog = None
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.write_back_called = False
        LandscapeClientSettingsDialog._write_back = self.real_write_back
        super(ConfigurationViewCommitTest, self).tearDown()

    def test_commit_fresh_dialog(self):
        """
        Test that we don't save anything from an untouched dialog on exit
        """
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.dialog._possibly_save_and_exit(None)
        self.assertFalse(self.write_back_called)

    def test_commit_hosted_account_name_change(self):
        """
        Test that we do save changes when we set a new account name for hosted
        accounts.
        """
        self.dialog._hosted_radiobutton.set_active(True)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.dialog._account_entry.set_text("glow")
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.dialog._possibly_save_and_exit(None)
        self.assertTrue(self.write_back_called)

    def test_commit_hosted_password_change(self):
        """
        Test that we do save changes when we set a new account name for hosted
        accounts.
        """
        self.dialog._hosted_radiobutton.set_active(True)
        self.dialog._password_entry.set_text("sticks")
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.dialog._possibly_save_and_exit(None)
        self.assertTrue(self.write_back_called)

    def test_commit_dedicated_server_host_name_change(self):
        """
        Test that we do save changes when we set a new server host name for
        a dedicated server.
        """
        self.dialog._dedicated_radiobutton.set_active(True)
        self.dialog._server_host_name_entry.set_text(
            "that.isolated.geographic")
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.dialog._possibly_save_and_exit(None)
        self.assertTrue(self.write_back_called)

    if not got_gobject_introspection:
        test_commit_dedicated_server_host_name_change.skip = \
            gobject_skip_message
        test_commit_hosted_password_change.skip = gobject_skip_message
        test_commit_hosted_account_name_change.skip = gobject_skip_message
        test_commit_fresh_dialog.skip = gobject_skip_message


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

    if not got_gobject_introspection:
        test_load_data_from_config.skip = gobject_skip_message
        test_init.skip = gobject_skip_message
