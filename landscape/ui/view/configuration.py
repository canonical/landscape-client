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
        self.__load_data()
        
    def __setup_ui(self):
        self.set_title("Landscape Client Settings")
        content_area = self.get_content_area()
        vbox = self.__builder.get_object(
            "landscape-client-settings-dialog-vbox")
        vbox.unparent()
        content_area.pack_start(vbox, expand=True, fill=True, padding=0)
        self._hosted_frame = self.__builder.get_object("hosted-frame")
        self._dedicated_frame = self.__builder.get_object("hosted-frame")
        self._hosted_radiobutton = self.__builder.get_object(
            "hosted-radiobutton")
        self._dedicated_radiobutton = self.__builder.get_object(
            "dedicated-radiobutton")
        self._account_entry = self.__builder.get_object("account-name-entry")
        self._password_entry = self.__builder.get_object(
            "reigstered-password-entry")
        self._server_host_name_entry = self.__builder.get_object(
            "server-host-name-entry")
        self._account_entry.set_sensitive(False)
        self._password_entry.set_sensitive(False)
        self._server_host_name_entry.set_sensitive(False)
        self._hosted_radiobutton.connect("toggled", 
                                    self.__on_toggle_server_type_radiobutton)
        self._dedicated_radiobutton.connect("toggled", 
                                    self.__on_toggle_server_type_radiobutton)
        self._revert_button = self.__builder.get_object("revert-button")
        self._revert_button.connect("clicked", self.revert)

    def __load_data(self):
        self._account_entry.set_text("")
        self._password_entry.set_text("")
        self._server_host_name_entry.set_text("")
        if self.controller.hosted:
            self._hosted_radiobutton.set_active(True)
            if not self.controller.account_name is None:
                self._account_entry.set_text(self.controller.account_name)
            if not self.controller.registration_password is None:
                self._password_entry.set_text(
                    self.controller.registration_password)
        else:
            self._dedicated_radiobutton.set_active(True)
            if not self.controller.server_host_name is None:
                self._server_host_name_entry.set_text(
                self.controller.server_host_name)
        self.select_landscape_hosting()


    def select_landscape_hosting(self):
        active = self._hosted_radiobutton.get_active()
        if active:
            self._account_entry.set_sensitive(True)
            self._password_entry.set_sensitive(True)
            self._server_host_name_entry.set_sensitive(False)
        else:
            self._account_entry.set_sensitive(False)
            self._password_entry.set_sensitive(False)
            self._server_host_name_entry.set_sensitive(True)
                
    def __on_toggle_server_type_radiobutton(self, radiobutton):
        self.select_landscape_hosting()
        return True

    def revert(self, button):
        self.controller.revert()
        self.__load_data()
        
        
        
        

