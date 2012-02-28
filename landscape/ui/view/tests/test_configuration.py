import sys

try:
    from gi.repository import Gtk, Gdk
    got_gobject_introspection = True
except (ImportError, RuntimeError):
    got_gobject_introspection = False
    gobject_skip_message = "GObject Introspection module unavailable"
else:
    del Gdk
    from landscape.ui.view.configuration import ClientSettingsDialog
    from landscape.ui.controller.configuration import ConfigController

from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import ConfigurationProxyHelper, FakeGSettings
from landscape.configuration import LandscapeSetupConfiguration
import landscape.ui.model.configuration.state
from landscape.ui.model.configuration.state import (
    COMPUTER_TITLE, ConfigurationModel)
from landscape.ui.model.configuration.uisettings import UISettings


class ConfigurationViewTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.default_data = {"management-type": "canonical",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": ""
                             }

        self.config_string = (
            "[client]\n"
            "data_path = %s\n"
            "http_proxy = http://proxy.localdomain:3192\n"
            "tags = a_tag\n"
            "url = https://landscape.canonical.com/message-system\n"
            "account_name = foo\n"
            "registration_password = bar\n"
            "computer_title = baz\n"
            "https_proxy = https://proxy.localdomain:6192\n"
            "ping_url = http://landscape.canonical.com/ping\n" % sys.path[0])

        super(ConfigurationViewTest, self).setUp()
        landscape.ui.model.configuration.state.DEFAULT_DATA[COMPUTER_TITLE] \
            = "me.here.com"
        settings = FakeGSettings(data=self.default_data)
        self.uisettings = UISettings(settings)
        model = ConfigurationModel(proxy=self.proxy,
                                   uisettings=self.uisettings)
        self.controller = ConfigController(model)

    def test_init(self):
        """
        Test that we correctly initialise the L{ConfigurationView} correctly
        from the controller.
        """
        dialog = ClientSettingsDialog(self.controller)
        content_area = dialog.get_content_area()
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertEqual(0, dialog.use_type_combobox.get_active())

    def test_on_combobox_changed(self):
        """
        Test that changes to the active selection in L{use_type_combobox}
        result in the correct panel becoming active and visible.
        """
        dialog = ClientSettingsDialog(self.controller)
        content_area = dialog.get_content_area()
        iter = dialog.liststore.get_iter(0)
        no_service_frame = dialog.liststore.get(iter, 2)[0]
        iter = dialog.liststore.get_iter(1)
        hosted_service_frame = dialog.liststore.get(iter, 2)[0]
        iter = dialog.liststore.get_iter(2)
        local_service_frame = dialog.liststore.get(iter, 2)[0]

        self.assertEqual(0, dialog.use_type_combobox.get_active())

        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(no_service_frame, dialog.active_widget)

        dialog.use_type_combobox.set_active(1)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(hosted_service_frame, dialog.active_widget)

        dialog.use_type_combobox.set_active(2)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(local_service_frame, dialog.active_widget)

    def test_load_data_from_config(self):
        """
        Test that we load data into the appropriate entries from the
        configuration file.
        """
        dialog = ClientSettingsDialog(self.controller)
        self.assertEqual(1, dialog.use_type_combobox.get_active())
        self.assertEqual("foo", dialog.hosted_account_name_entry.get_text())
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())
        self.assertEqual("", dialog.local_landscape_host_entry.get_text())
        self.assertEqual("", dialog.local_account_name_entry.get_text())
        self.assertEqual("", dialog.local_password_entry.get_text())

    def test_revert(self):
        """
        Test that we can revert the UI values using the controller.
        """
        dialog = ClientSettingsDialog(self.controller)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(1, dialog.use_type_combobox.get_active())
        self.assertEqual("foo", dialog.hosted_account_name_entry.get_text())
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())
        dialog.use_type_combobox.set_active(2)
        dialog.local_landscape_host_entry.set_text("more.barn")
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual("standalone", dialog.local_account_name_entry.get_text())
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())
        self.assertEqual("more.barn",
                         dialog.local_landscape_host_entry.get_text())
        dialog.revert(None)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(1, dialog.use_type_combobox.get_active())
        self.assertEqual("foo", dialog.hosted_account_name_entry.get_text())
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())

        # self.assertEqual("foo", dialog._account_entry.get_text())
        # self.assertEqual("bar", dialog._password_entry.get_text())
        # self.assertEqual("landscape.canonical.com",
        #                  dialog._server_host_name_entry.get_text())
        # self.assertFalse(dialog._dedicated_radiobutton.get_active())
        # self.assertTrue(dialog._hosted_radiobutton.get_active())

    if not got_gobject_introspection:
        test_revert.skip = gobject_skip_message
        test_load_data_from_config.skip = gobject_skip_message
        test_toggle_radio_button.skip = gobject_skip_message
        test_init.skip = gobject_skip_message
        test_modification.skip = gobject_skip_message


class ConfigurationViewCommitTest(LandscapeTest):

    def setUp(self):
        super(ConfigurationViewCommitTest, self).setUp()
        config = "[client]\n"
        config += "data_path = %s\n" % sys.path[0]
        config += "http_proxy = http://proxy.localdomain:3192\n"
        config += "tags = a_tag\n"
        config += "url = https://landscape.canonical.com/message-system\n"
        config += "account_name = foo\n"
        config += "registration_password = bar\n"
        config += "computer_title = baz\n"
        config += "https_proxy = https://proxy.localdomain:6192\n"
        config += "ping_url = http://landscape.canonical.com/ping\n"
        self.config_filename = self.makeFile(config)

        class MySetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]

        self.config = MySetupConfiguration()
        self.real_write_back = ClientSettingsDialog._write_back
        self.write_back_called = False

        def fake_write_back(obj):
            self.write_back_called = True

        ClientSettingsDialog._write_back = fake_write_back
        self.controller = ConfigController(self.config)
        self.dialog = ClientSettingsDialog(self.controller)

    def tearDown(self):
        self.controller = None
        self.dialog.destroy()
        self.dialog = None
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.write_back_called = False
        ClientSettingsDialog._write_back = self.real_write_back
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
        config = "[client]\n"
        config += "data_path = %s\n" % sys.path[0]
        config += "url = https://landscape.localdomain/message-system\n"
        config += "computer_title = baz\n"
        config += "ping_url = http://landscape.localdomain/ping\n"
        self.config_filename = self.makeFile(config)

        class MySetupConfiguration(LandscapeSetupConfiguration):
            default_config_filenames = [self.config_filename]

        self.config = MySetupConfiguration()

    def test_init(self):
        """
        Test that we correctly initialise the L{ConfigurationView} correctly
        from the controller.
        """
        controller = ConfigController(self.config)
        dialog = ClientSettingsDialog(controller)
        content_area = dialog.get_content_area()
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertFalse(dialog._hosted_radiobutton.get_active())
        self.assertTrue(dialog._dedicated_radiobutton.get_active())
        self.assertTrue(dialog._account_entry.get_sensitive())
        self.assertTrue(dialog._password_entry.get_sensitive())
        self.assertTrue(dialog._server_host_name_entry.get_sensitive())

    def test_load_data_from_config(self):
        """
        Test that we load data into the appropriate entries from the
        configuration file.
        """
        controller = ConfigController(self.config)
        dialog = ClientSettingsDialog(controller)
        self.assertEqual("", dialog._account_entry.get_text())
        self.assertEqual("", dialog._password_entry.get_text())
        self.assertEqual("landscape.localdomain",
                         dialog._server_host_name_entry.get_text())

    if not got_gobject_introspection:
        test_load_data_from_config.skip = gobject_skip_message
        test_init.skip = gobject_skip_message
