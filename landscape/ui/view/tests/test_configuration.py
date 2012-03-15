import sys

from landscape.ui.tests.helpers import (
    ConfigurationProxyHelper, FakeGSettings, gobject_skip_message,
    got_gobject_introspection, simulate_gtk_key_release)

if got_gobject_introspection:
    from gi.repository import Gtk, Gdk
    from landscape.ui.view.configuration import ClientSettingsDialog
    from landscape.ui.controller.configuration import ConfigController
    import landscape.ui.model.configuration.state
    from landscape.ui.model.configuration.state import (
        COMPUTER_TITLE, ConfigurationModel)
    from landscape.ui.model.configuration.uisettings import UISettings

from landscape.tests.helpers import LandscapeTest


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
                             "local-password": ""}

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
        self.assertEqual("preferences-management-service",
                        dialog.get_default_icon_name())
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertEqual(1, dialog.use_type_combobox.get_active())

    def test_on_combobox_changed(self):
        """
        Test that changes to the active selection in L{use_type_combobox}
        result in the correct panel becoming active and visible.
        """
        dialog = ClientSettingsDialog(self.controller)
        iter = dialog.liststore.get_iter(0)
        no_service_frame = dialog.liststore.get(iter, 2)[0]
        iter = dialog.liststore.get_iter(1)
        hosted_service_frame = dialog.liststore.get(iter, 2)[0]
        iter = dialog.liststore.get_iter(2)
        local_service_frame = dialog.liststore.get(iter, 2)[0]

        self.assertEqual(1, dialog.use_type_combobox.get_active())
        [alignment] = dialog.register_button.get_children()
        [hbox] = alignment.get_children()
        [image, label] = hbox.get_children()

        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(hosted_service_frame, dialog.active_widget)
        self.assertEqual(dialog.REGISTER_BUTTON_TEXT, label.get_text())

        dialog.use_type_combobox.set_active(0)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(no_service_frame, dialog.active_widget)
        self.assertEqual(dialog.DISABLE_BUTTON_TEXT, label.get_text())

        dialog.use_type_combobox.set_active(2)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertIs(local_service_frame, dialog.active_widget)
        self.assertEqual(dialog.REGISTER_BUTTON_TEXT, label.get_text())

    def test_modify(self):
        """
        Test that modifications to data in the UI are propagated to the
        controller.
        """
        dialog = ClientSettingsDialog(self.controller)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertFalse(self.controller.is_modified)
        self.assertEqual(1, dialog.use_type_combobox.get_active())
        dialog.use_type_combobox.set_active(2)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertTrue(self.controller.is_modified)
        dialog.revert(None)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertFalse(self.controller.is_modified)
        simulate_gtk_key_release(dialog, dialog.hosted_account_name_entry,
                                 Gdk.KEY_A)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertTrue(self.controller.is_modified)
        dialog.revert(None)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertFalse(self.controller.is_modified)
        simulate_gtk_key_release(dialog, dialog.hosted_password_entry,
                               Gdk.KEY_A)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertTrue(self.controller.is_modified)
        dialog.revert(None)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertFalse(self.controller.is_modified)
        simulate_gtk_key_release(dialog, dialog.local_landscape_host_entry,
                               Gdk.KEY_A)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertTrue(self.controller.is_modified)

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
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())
        self.assertEqual("more.barn",
                         dialog.local_landscape_host_entry.get_text())
        dialog.revert(None)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(1, dialog.use_type_combobox.get_active())
        self.assertEqual("foo", dialog.hosted_account_name_entry.get_text())
        self.assertEqual("bar", dialog.hosted_password_entry.get_text())

    if not got_gobject_introspection:
        skip = gobject_skip_message


class LocalConfigurationViewTest(LandscapeTest):

    helpers = [ConfigurationProxyHelper]

    def setUp(self):
        self.default_data = {"management-type": "LDS",
                             "computer-title": "",
                             "hosted-landscape-host": "",
                             "hosted-account-name": "",
                             "hosted-password": "",
                             "local-landscape-host": "",
                             "local-account-name": "",
                             "local-password": "manky"}

        self.config_string = (
            "[client]\n"
            "data_path = %s\n"
            "url = https://landscape.localdomain/message-system\n"
            "computer_title = baz\n"
            "ping_url = http://landscape.localdomain/ping\n" % sys.path[0])

        super(LocalConfigurationViewTest, self).setUp()
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
        while Gtk.events_pending():
            Gtk.main_iteration()
        content_area = dialog.get_content_area()
        children = content_area.get_children()
        self.assertEqual(len(children), 2)
        box = children[0]
        self.assertIsInstance(box, Gtk.Box)
        self.assertEqual(2, dialog.use_type_combobox.get_active())

    def test_load_data_from_config(self):
        """
        Test that we load data into the appropriate entries from the
        configuration file.
        """
        dialog = ClientSettingsDialog(self.controller)
        while Gtk.events_pending():
            Gtk.main_iteration()
        self.assertEqual(2, dialog.use_type_combobox.get_active())
        self.assertEqual("", dialog.hosted_account_name_entry.get_text())
        self.assertEqual("", dialog.hosted_password_entry.get_text())
        self.assertEqual("landscape.localdomain",
                         dialog.local_landscape_host_entry.get_text())
        self.assertEqual("manky", dialog.local_password_entry.get_text())

    if not got_gobject_introspection:
        skip = gobject_skip_message
