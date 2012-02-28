import os

from gi.repository import GObject, Gtk

from landscape.ui.constants import (
    CANONICAL_MANAGED, LOCAL_MANAGED, NOT_MANAGED)



class ClientSettingsDialog(Gtk.Dialog):

    GLADE_FILE = "landscape-client-settings.glade"
    NO_SERVICE_TEXT = "Do not manage this computer with Landscape."
    HOSTED_SERVICE_TEXT = "Use Canonical's hosted Landscape service."
    LOCAL_SERVICE_TEXT = "Use a dedicated Landscape system."

    def __init__(self, controller):
        super(ClientSettingsDialog, self).__init__(
            title="Management Service",
            flags=Gtk.DialogFlags.MODAL,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OK, Gtk.ResponseType.OK))
        self.controller = controller
        self.setup_ui()
        self.load_data()

    def _set_use_type_combobox_from_controller(self):        
        iter = self.liststore.get_iter_first()
        while self.liststore.get(iter, 0)[0] != self.controller.management_type:
            iter = self.liststore.iter_next(iter)
        path = self.liststore.get_path(iter)
        [index] = path.get_indices()
        self.use_type_combobox.set_active(index)

    def _set_hosted_values_from_controller(self):
        self.hosted_account_name_entry.set_text(
            self.controller.hosted_account_name)
        self.hosted_password_entry.set_text(self.controller.hosted_password)

    def _set_local_values_from_controller(self):
        self.local_landscape_host_entry.set_text(
            self.controller.local_landscape_host)
        self.local_account_name_entry.set_text(
            self.controller.local_account_name)
        self.local_password_entry.set_text(self.controller.local_password)

    def load_data(self):
        self.controller.load()
        self._set_hosted_values_from_controller()
        self._set_local_values_from_controller()
        self._set_use_type_combobox_from_controller()

    def make_liststore(self):
        liststore = Gtk.ListStore(GObject.TYPE_PYOBJECT,
                                  GObject.TYPE_STRING,
                                  GObject.TYPE_PYOBJECT)
        self.active_widget = None
        liststore.append([NOT_MANAGED, self.NO_SERVICE_TEXT,
                          self._builder.get_object("no-service-frame")])
        liststore.append([CANONICAL_MANAGED, self.HOSTED_SERVICE_TEXT,
                          self._builder.get_object("hosted-service-frame")])
        liststore.append([LOCAL_MANAGED, self.LOCAL_SERVICE_TEXT,
                          self._builder.get_object("local-service-frame")])
        return liststore

    def link_hosted_service_widgets(self):
        self.hosted_account_name_entry = self._builder.get_object(
            "hosted-account-name-entry")
        self.hosted_password_entry = self._builder.get_object(
            "hosted-password-entry")

    def link_local_service_widgets(self):
        self.local_landscape_host_entry = self._builder.get_object(
            "local-landscape-host-entry")
        self.local_account_name_entry = self._builder.get_object(
            "local-account-name-entry")
        self.local_password_entry = self._builder.get_object(
            "local-password-entry")

    def link_use_type_combobox(self, liststore):
        self.use_type_combobox = self._builder.get_object("use-type-combobox")
        self.use_type_combobox.connect("changed", self.on_combo_changed)
        self.use_type_combobox.set_model(liststore)
        cell = Gtk.CellRendererText()
        self.use_type_combobox.pack_start(cell, True)
        self.use_type_combobox.add_attribute(cell, 'text', 1)
        
    def setup_ui(self):
        self._builder = Gtk.Builder()
        self._builder.add_from_file(
            os.path.join(
                os.path.dirname(__file__), "ui", self.GLADE_FILE))
        content_area = self.get_content_area()
        content_area.set_spacing(12)
        self.set_border_width(12)
        self._vbox = self._builder.get_object("toplevel-vbox")
        self._vbox.unparent()
        content_area.pack_start(self._vbox, expand=True, fill=True, padding=12)
        self.liststore = self.make_liststore()
        self.link_use_type_combobox(self.liststore)
        self.link_hosted_service_widgets()
        self.link_local_service_widgets()
        revert_button = Gtk.Button(stock=Gtk.STOCK_REVERT_TO_SAVED)
        self.action_area.pack_start(revert_button, True, True, 0)
        self.action_area.reorder_child(revert_button, 0)
        revert_button.connect("clicked", self.revert)
        revert_button.show()
        self.connect("destroy",  self.quit)
        self.connect("delete-event",  self.quit)

    def on_combo_changed(self, combobox):
        iter = self.liststore.get_iter(combobox.get_active())
        if not self.active_widget is None:
            self._vbox.remove(self.active_widget)
        self.active_widget = self.liststore.get(iter, 2)[0]
        self.active_widget.unparent()
        self._vbox.add(self.active_widget)

    def quit(self, *args):
        self.destroy()

    def revert(self, button):
        self.controller.revert()
        self.load_data()


# if __name__ == "__main__":
#     dialog = ClientSettingsDialog()
#     response = dialog.run()
#     if response == Gtk.ResponseType.OK:
#         print "Would have saved"
#     else:
#         print "Would not have saved"


# import os

# from gi.repository import Gtk, Gdk


# class ClientSettingsDialog(Gtk.Dialog):

#     GLADE_FILE = "landscape-client-settings.glade"

#     def __init__(self, controller):
#         super(ClientSettingsDialog, self).__init__()
#         self._continue = False
#         self.controller = controller
#         self.controller.register_observer(self._on_modify)
#         self._ui_path = os.path.join(
#             os.path.dirname(__file__), "ui",
#             ClientSettingsDialog.GLADE_FILE)
#         self._builder = Gtk.Builder()
#         self._builder.add_from_file(self._ui_path)
#         self._setup_ui()
#         self._hosted_toggle = None
#         self._dedicated_toggle = None
#         self.revert(self._revert_button)

#     def _setup_window(self):
#         """
#         Configure the dialog window and pack content from the Glade UI file
#         into the main content area.
#         """
#         self.set_title("Management Service Settings")
#         content_area = self.get_content_area()
#         vbox = self._builder.get_object(
#             "landscape-client-settings-dialog-vbox")
#         vbox.unparent()
#         content_area.pack_start(vbox, expand=True, fill=True, padding=0)

#     def _setup_action_buttons(self):
#         """
#         Obtain handles for action buttons and connect them to handlers.
#         """
#         self._close_button = self._builder.get_object("close-button")
#         self._revert_button = self._builder.get_object("revert-button")
#         self._revert_button.connect("clicked", self.revert)
#         self._close_button.connect("clicked", self._possibly_save_and_exit)

#     def _setup_registration_controls(self):
#         """
#         Obtain handles for controls relating to the registration process.
#         """
#         self._registration_button = self._builder.get_object(
#             "registration-button")
#         self._registration_image = self._builder.get_object(
#             "registration-image")
#         self._registration_textbuffer = self._builder.get_object(
#             "registration-textbuffer")
#         self._registration_button.connect("clicked", self._register)

#     def _setup_entries(self):
#         """
#         Obtain handles for entry widgets, set initial state and connect them to
#         handlers.
#         """
#         self._account_entry = self._builder.get_object("account-name-entry")
#         self._password_entry = self._builder.get_object(
#             "password-entry")
#         self._server_host_name_entry = self._builder.get_object(
#             "server-host-name-entry")
#         self._server_host_name_entry.set_sensitive(False)
#         self._account_entry.connect("changed", self._update_account)
#         self._password_entry.connect("changed", self._update_password)
#         self._server_host_name_entry.connect("changed",
#                                              self._update_server_host_name)

#     def _setup_radiobuttons(self):
#         """
#         Obtain handles on radiobuttons and connect them to handler.
#         """
#         self._hosted_radiobutton = self._builder.get_object(
#             "hosted-radiobutton")
#         self._dedicated_radiobutton = self._builder.get_object(
#             "dedicated-radiobutton")

#     def _setup_ui(self):
#         self._setup_window()
#         self._setup_radiobuttons()
#         self._setup_entries()
#         self._setup_action_buttons()
#         self._setup_registration_controls()

#     def _load_data(self):
#         """
#         Pull data up from the controller into the view widgets.  Note that we
#         don't want to propagate events back to the controller as this will set
#         up an infinite loop - hence the lock.
#         """
#         self.controller.lock()
#         if not self.controller.account_name is None:
#             self._account_entry.set_text(self.controller.account_name)
#         if not self.controller.registration_password is None:
#             self._password_entry.set_text(
#                 self.controller.registration_password)
#         if not self.controller.server_host_name is None:
#             self._server_host_name_entry.set_text(
#                 self.controller.server_host_name)
#         self.controller.unlock()

#     def _update_account(self, event):
#         if not self.controller.is_locked():
#             self.controller.account_name = self._account_entry.get_text()

#     def _update_password(self, event):
#         if not self.controller.is_locked():
#             self.controller.registration_password = \
#                 self._password_entry.get_text()

#     def _update_server_host_name(self, event):
#         if not self.controller.is_locked():
#             self.controller.server_host_name = \
#                 self._server_host_name_entry.get_text()

#     def _set_entry_sensitivity(self, hosted):
#         self._server_host_name_entry.set_sensitive(not hosted)

#     def select_landscape_hosting(self):
#         hosted = self._hosted_radiobutton.get_active()
#         self._set_entry_sensitivity(hosted)
#         if hosted:
#             self.controller.default_hosted()
#             self._load_data()
#         else:
#             self.controller.default_dedicated()
#             self._load_data()

#     def _on_toggle_server_type_radiobutton(self, radiobutton):
#         self.select_landscape_hosting()
#         return True

#     def revert(self, button):
#         self.controller.revert()
#         if self._hosted_toggle:
#             self._hosted_radiobutton.disconnect(self._hosted_toggle)
#         if self._dedicated_toggle:
#             self._dedicated_radiobutton.disconnect(self._dedicated_toggle)
#         if self.controller.hosted:
#             self._hosted_radiobutton.set_active(True)
#         else:
#             self._dedicated_radiobutton.set_active(True)
#         self._set_entry_sensitivity(self.controller.hosted)
#         self._load_data()
#         self._hosted_toggle = self._hosted_radiobutton.connect(
#             "toggled",
#             self._on_toggle_server_type_radiobutton)
#         self._dedicated_toggle = self._dedicated_radiobutton.connect(
#             "toggled",
#             self._on_toggle_server_type_radiobutton)

#     def _write_back(self):
#         self.controller.commit()

#     def _possibly_save_and_exit(self, button):
#         """
#         Write back if something has been modified.
#         """
#         if self.controller.is_modified:
#             self._write_back()
#         self.destroy()

#     def _process_gtk_events(self):
#         """
#         Deal with any outstanding Gtk events.  Used to keep the GUI ticking
#         over during long running activities.
#         """
#         while Gtk.events_pending():
#             Gtk.main_iteration()

#     def _registration_message(self, message):
#         self._registration_textbuffer.insert_at_cursor(message)
#         self._registration_image.set_from_stock(Gtk.STOCK_DIALOG_INFO, 4)
#         self._process_gtk_events()

#     def _registration_error(self, error):
#         self._registration_textbuffer.insert_at_cursor(str(error))
#         self._registration_image.set_from_stock(Gtk.STOCK_DIALOG_WARNING, 4)
#         self._process_gtk_events()

#     def _registration_succeed(self, message):
#         self._registration_textbuffer.insert_at_cursor(str(message))
#         self._registration_image.set_from_stock(Gtk.STOCK_CONNECT, 4)
#         self._close_button.set_sensitive(True)
#         self._set_normal_cursor()

#     def _registration_fail(self, error=None):
#         if error:
#             self._registration_textbuffer.insert_at_cursor(str(error))
#         self._registration_image.set_from_stock(Gtk.STOCK_DISCONNECT, 4)
#         self._set_normal_cursor()

#     def _set_wait_cursor(self):
#         watch = Gdk.Cursor(Gdk.CursorType.WATCH)
#         self.get_window().set_cursor(watch)
#         self._process_gtk_events()

#     def _set_normal_cursor(self):
#         arrow = Gdk.Cursor(Gdk.CursorType.ARROW)
#         self.get_window().set_cursor(arrow)
#         self._process_gtk_events()

#     def _register(self, button):
#         self._set_wait_cursor()
#         self._write_back()
#         self._registration_image.set_from_stock(Gtk.STOCK_CONNECT, 4)
#         self.controller.register(self._registration_message,
#                                  self._registration_error,
#                                  self._registration_succeed,
#                                  self._registration_fail,
#                                  self._process_gtk_events)

#     def _on_modify(self, modified):
#         self._close_button.set_sensitive(not modified)
#         if modified:
#             self._registration_image.set_from_stock(Gtk.STOCK_DISCONNECT, 4)
#             self._registration_textbuffer.set_text("")
