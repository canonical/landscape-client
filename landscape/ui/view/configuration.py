import os

from gi.repository import Gtk

class LandscapeClientSettingsDialog(Gtk.Dialog):

    GLADE_FILE = "landscape-client-settings.glade"
    
    def __init__(self, controller, data_path=None, *args, **kwargs):
        super(LandscapeClientSettingsDialog, self).__init__(*args, **kwargs)
        self.controller = controller
        if data_path is None:
            self.__ui_path = os.path.join(
                controller.data_path, "ui",
                LandscapeClientSettingsDialog.GLADE_FILE)
        else:
            self.__ui_path = os.path.join(
                data_path, "ui",
                LandscapeClientSettingsDialog.GLADE_FILE)
        self.__builder = Gtk.Builder()
        self.__builder.add_from_file(self.__ui_path)
        self.__setup_ui()
        self._hosted_toggle = None
        self._dedicated_toggle = None
        self.revert(self._revert_button)
        # self.select_landscape_hosting()
 
    def __setup_window(self):
        """
        Configure the dialog window and pack content from the Glade UI file
        into the main content area.
        """
        self.set_title("Landscape Client Settings")
        content_area = self.get_content_area()
        vbox = self.__builder.get_object(
            "landscape-client-settings-dialog-vbox")
        vbox.unparent()
        content_area.pack_start(vbox, expand=True, fill=True, padding=0)

    def __setup_action_buttons(self):
        """
        Obtain handles for action buttons and connect them to handlers.
        """
        self._close_button = self.__builder.get_object("close-button")
        self._revert_button = self.__builder.get_object("revert-button")
        self._revert_button.connect("clicked", self.revert)
        self._close_button.connect("clicked", self._possibly_save_and_exit)


    def __setup_entries(self):
        """
        Obtain handles for entry widgets, set initial state and connect them to
        handlers.
        """
        self._account_entry = self.__builder.get_object("account-name-entry")
        self._password_entry = self.__builder.get_object(
            "reigstered-password-entry")
        self._server_host_name_entry = self.__builder.get_object(
            "server-host-name-entry")
        self._account_entry.set_sensitive(False)
        self._password_entry.set_sensitive(False)
        self._server_host_name_entry.set_sensitive(False)
        self._account_entry.connect("changed", self._update_account)
        self._password_entry.connect("changed", self._update_password)
        self._server_host_name_entry.connect("changed", 
                                             self._update_server_host_name)


    def __setup_radiobuttons(self):
        """
        Obtain handles on radiobuttons and connect them to handler.
        """
        self._hosted_radiobutton = self.__builder.get_object(
            "hosted-radiobutton")
        self._dedicated_radiobutton = self.__builder.get_object(
            "dedicated-radiobutton")

    def __setup_ui(self):
        self.__setup_window()
        self.__setup_radiobuttons()
        self.__setup_entries()
        self.__setup_action_buttons()

    def __load_data(self):
        self.controller.lock()
        if not self.controller.account_name is None:
            self._account_entry.set_text(self.controller.account_name)
        if not self.controller.registration_password is None:
            self._password_entry.set_text(
                self.controller.registration_password)
        if not self.controller.server_host_name is None:
            self._server_host_name_entry.set_text(
                self.controller.server_host_name)
        self.controller.unlock()

    def _update_account(self, event):
        if not self.controller.is_locked():
            self.controller.account_name = self._account_entry.get_text()
    
    def _update_password(self, event):
        if not self.controller.is_locked():
            self.controller.registration_password = \
                self._password_entry.get_text()
    
    def _update_server_host_name(self, event):
        if not self.controller.is_locked():
            self.controller.server_host_name = \
                self._server_host_name_entry.get_text()

    def __set_entry_sensitivity(self, hosted):
        if hosted:
            self._account_entry.set_sensitive(True)
            self._password_entry.set_sensitive(True)
            self._server_host_name_entry.set_sensitive(False)
        else:
            self._account_entry.set_sensitive(False)
            self._password_entry.set_sensitive(False)
            self._server_host_name_entry.set_sensitive(True)

    def select_landscape_hosting(self):
        hosted = self._hosted_radiobutton.get_active()
        self.__set_entry_sensitivity(hosted)
        if hosted:
            self.controller.default_hosted()
            self.__load_data()
        else:
            self.controller.default_dedicated()
            self.__load_data()
                
    def __on_toggle_server_type_radiobutton(self, radiobutton):
        self.select_landscape_hosting()
        return True

    def revert(self, button):
        self.controller.revert()
        if self._hosted_toggle:
            self._hosted_radiobutton.disconnect(self._hosted_toggle)
        if self._dedicated_toggle:
            self._dedicated_radiobutton.disconnect(self._dedicated_toggle)
        if self.controller.hosted:
            self._hosted_radiobutton.set_active(True)
        else:
            self._dedicated_radiobutton.set_active(True)
        self.__set_entry_sensitivity(self.controller.hosted)
        self.__load_data()
        self._hosted_toggle = self._hosted_radiobutton.connect(
            "toggled", 
            self.__on_toggle_server_type_radiobutton)
        self._dedicated_toggle = self._dedicated_radiobutton.connect(
            "toggled", 
            self.__on_toggle_server_type_radiobutton)


    def _write_back(self):
        self.controller.commit()

    def _possibly_save_and_exit(self, button):
        if self.controller.is_modified:
            self._write_back()
        self.destroy()
