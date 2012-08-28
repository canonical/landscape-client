import re
import os

from gettext import gettext as _

from gi.repository import GObject, Gtk

from landscape.ui.constants import (
    CANONICAL_MANAGED, LOCAL_MANAGED, NOT_MANAGED)

# Note, I think this may not be fully compliant with the changes in RFC 1123
HOST_NAME_REGEXP = re.compile("^(([a-zA-Z][a-zA-Z0-9\-]*)?[a-zA-Z0-9][\.]?)*"
                              "(([A-Za-z][A-Za-z0-9\-]*)?[A-Za-z0-9])$")


def sanitise_host_name(host_name):
    """
    Do some minimal host name sanitation.
    """
    return host_name.strip()


def is_valid_host_name(host_name):
    """
    Check that the provided host name complies with L{HOST_NAME_REGEXP} and is
    therefor valid.
    """
    return HOST_NAME_REGEXP.match(host_name) is not None


def is_ascii(text):
    """
    Test that the provided string contains only characters from the ASCII set.
    """
    try:
        text.decode("ascii")
        return True
    except UnicodeDecodeError:
        return False


class ClientSettingsDialog(Gtk.Dialog):
    """
    L{ClientSettingsDialog} is a subclass of Gtk.Dialog that loads the UI
    components from the associated Glade XML file and wires everything up to
    the controller.
    """

    GLADE_FILE = "landscape-client-settings.glade"
    INVALID_HOST_NAME = 0
    UNICODE_IN_ENTRY = 1

    def __init__(self, controller):
        super(ClientSettingsDialog, self).__init__(
            title=_("Landscape Service"),
            flags=Gtk.DialogFlags.MODAL)
        self.set_default_icon_name("preferences-management-service")
        self.set_resizable(False)
        self._initialised = False
        self._validation_errors = set()
        self._errored_entries = []
        self.controller = controller
        self.setup_ui()
        self.load_data()
        # One extra revert to reset after loading data
        self.controller.revert()

    def indicate_error_on_entry(self, entry):
        """
        Show a warning icon on a L{Gtk.Entry} to indicate some associated
        error.
        """
        entry.set_icon_from_stock(
            Gtk.EntryIconPosition.PRIMARY, Gtk.STOCK_DIALOG_WARNING)
        self._errored_entries.append(entry)

    def check_local_landscape_host_name_entry(self):
        host_name = sanitise_host_name(
            self.local_landscape_host_entry.get_text())
        ascii_ok = is_ascii(host_name)
        host_name_ok = is_valid_host_name(host_name)
        if ascii_ok and host_name_ok:
            self.local_landscape_host_entry.set_text(host_name)
            return True
        else:
            self.indicate_error_on_entry(self.local_landscape_host_entry)
            if not host_name_ok:
                self._validation_errors.add(self.INVALID_HOST_NAME)
            if not ascii_ok:
                self._validation_errors.add(self.UNICODE_IN_ENTRY)
            return False

    def check_entry(self, entry):
        """
        Check that the text content of a L{Gtk.Entry} is acceptable.
        """
        if is_ascii(entry.get_text()):
            return True
        else:
            self.indicate_error_on_entry(entry)
            self._validation_errors.add(self.UNICODE_IN_ENTRY)
            return False

    def validity_check(self):
        self._validation_errors = set()
        if self._info_bar_container.get_visible():
            self.dismiss_infobar(None)
        active_iter = self.liststore.get_iter(
            self.use_type_combobox.get_active())
        [management_type] = self.liststore.get(active_iter, 0)
        if management_type == NOT_MANAGED:
            return True
        elif management_type == CANONICAL_MANAGED:
            account_name_ok = self.check_entry(self.hosted_account_name_entry)
            password_ok = self.check_entry(self.hosted_password_entry)
            return account_name_ok and password_ok
        else:
            host_name_ok = self.check_local_landscape_host_name_entry()
            password_ok = self.check_entry(self.local_password_entry)
            return host_name_ok and password_ok

    @property
    def NO_SERVICE_TEXT(self):
        return _("None")

    @property
    def HOSTED_SERVICE_TEXT(self):
        return _("Landscape - hosted by Canonical")

    @property
    def LOCAL_SERVICE_TEXT(self):
        return _("Landscape - dedicated server")

    @property
    def REGISTER_BUTTON_TEXT(self):
        return _("Register")

    @property
    def DISABLE_BUTTON_TEXT(self):
        return _("Disable")

    @property
    def INVALID_HOST_NAME_MESSAGE(self):
        return _("Invalid host name.")

    @property
    def UNICODE_IN_ENTRY_MESSAGE(self):
        return _("Only ASCII characters are allowed.")

    def _set_use_type_combobox_from_controller(self):
        """
        Load the persisted L{management_type} from the controller and set the
        combobox appropriately.

        Note that Gtk makes us jump through some hoops by having it's own model
        level to deal with here.  The conversion between paths and iters makes
        more sense if you understand that treeviews use the same model.
        """
        list_iter = self.liststore.get_iter_first()
        while (self.liststore.get(list_iter, 0)[0] !=
               self.controller.management_type):
            list_iter = self.liststore.iter_next(list_iter)
        path = self.liststore.get_path(list_iter)
        [index] = path.get_indices()
        self.use_type_combobox.set_active(index)

    def _set_hosted_values_from_controller(self):
        self.hosted_account_name_entry.set_text(
            self.controller.hosted_account_name)
        self.hosted_password_entry.set_text(self.controller.hosted_password)

    def _set_local_values_from_controller(self):
        self.local_landscape_host_entry.set_text(
            self.controller.local_landscape_host)
        self.local_password_entry.set_text(self.controller.local_password)

    def load_data(self):
        self._initialised = False
        self.controller.load()
        self._set_hosted_values_from_controller()
        self._set_local_values_from_controller()
        self._set_use_type_combobox_from_controller()
        self._initialised = True

    def make_liststore(self):
        """
        Construct the correct L{Gtk.ListStore} to drive the L{Gtk.ComboBox} for
        use-type.  This a table of:

           * Management type (key)
           * Text to display in the combobox
           * L{Gtk.Frame} to load when this item is selected.
        """
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
        self.hosted_account_name_entry.connect(
            "changed", self.on_changed_event, "hosted_account_name")

        self.hosted_password_entry = self._builder.get_object(
            "hosted-password-entry")
        self.hosted_password_entry.connect(
            "changed", self.on_changed_event, "hosted_password")

    def link_local_service_widgets(self):
        self.local_landscape_host_entry = self._builder.get_object(
            "local-landscape-host-entry")
        self.local_landscape_host_entry.connect(
            "changed", self.on_changed_event, "local_landscape_host")

        self.local_password_entry = self._builder.get_object(
            "local-password-entry")
        self.local_password_entry.connect(
            "changed", self.on_changed_event, "local_password")

    def link_use_type_combobox(self, liststore):
        self.use_type_combobox = self._builder.get_object("use-type-combobox")
        self.use_type_combobox.connect("changed", self.on_combo_changed)
        self.use_type_combobox.set_model(liststore)
        cell = Gtk.CellRendererText()
        self.use_type_combobox.pack_start(cell, True)
        self.use_type_combobox.add_attribute(cell, 'text', 1)

    def cancel_response(self, widget):
        self.response(Gtk.ResponseType.CANCEL)

    def register_response(self, widget):
        if self.validity_check():
            self.response(Gtk.ResponseType.OK)
        else:
            error_text = []
            if self.UNICODE_IN_ENTRY in self._validation_errors:
                error_text.append(self.UNICODE_IN_ENTRY_MESSAGE)
            if self.INVALID_HOST_NAME in self._validation_errors:
                error_text.append(self.INVALID_HOST_NAME_MESSAGE)
            self.info_message.set_text("\n".join(error_text))
            self._info_bar_container.show()

    def set_button_text(self, management_type):
        [alignment] = self.register_button.get_children()
        [hbox] = alignment.get_children()
        [image, label] = hbox.get_children()
        if management_type == NOT_MANAGED:
            label.set_text(self.DISABLE_BUTTON_TEXT)
        else:
            label.set_text(self.REGISTER_BUTTON_TEXT)

    def setup_buttons(self):
        self.revert_button = Gtk.Button(stock=Gtk.STOCK_REVERT_TO_SAVED)
        self.action_area.pack_start(self.revert_button, True, True, 0)
        self.revert_button.connect("clicked", self.revert)
        self.revert_button.show()
        self.cancel_button = Gtk.Button(stock=Gtk.STOCK_CANCEL)
        self.action_area.pack_start(self.cancel_button, True, True, 0)
        self.cancel_button.show()
        self.cancel_button.connect("clicked", self.cancel_response)
        self.register_button = Gtk.Button(stock=Gtk.STOCK_OK)
        self.action_area.pack_start(self.register_button, True, True, 0)
        self.register_button.show()
        self.register_button.connect("clicked", self.register_response)

    def dismiss_infobar(self, widget):
        self._info_bar_container.hide()
        for entry in self._errored_entries:
            entry.set_icon_from_stock(Gtk.EntryIconPosition.PRIMARY, None)
        self._errored_entries = []

    def setup_info_bar(self):
        labels_size_group = self._builder.get_object("labels-sizegroup")
        entries_size_group = self._builder.get_object("entries-sizegroup")
        labels_size_group.set_ignore_hidden(False)
        entries_size_group.set_ignore_hidden(False)
        self._info_bar_container = Gtk.HBox()
        self._info_bar_container.set_spacing(12)
        info_bar = Gtk.InfoBar()
        entries_size_group.add_widget(info_bar)
        info_bar.show()
        empty_label = Gtk.Label()
        labels_size_group.add_widget(empty_label)
        empty_label.show()
        self._info_bar_container.pack_start(empty_label, expand=False,
                                            fill=False, padding=0)
        self._info_bar_container.pack_start(info_bar, expand=False, fill=False,
                                            padding=0)
        content_area = info_bar.get_content_area()
        hbox = Gtk.HBox()
        self.info_message = Gtk.Label()
        self.info_message.set_alignment(0, 0.5)
        self.info_message.show()
        hbox.pack_start(self.info_message, expand=True, fill=True, padding=6)
        ok_button = Gtk.Button("Dismiss")
        ok_button.connect("clicked", self.dismiss_infobar)
        ok_button.show()
        hbox.pack_start(ok_button, expand=True, fill=True, padding=0)
        hbox.show()
        content_area.pack_start(hbox, expand=True, fill=True, padding=0)

    def setup_ui(self):
        self._builder = Gtk.Builder()
        self._builder.set_translation_domain("landscape-client")
        self._builder.add_from_file(
            os.path.join(
                os.path.dirname(__file__), "ui", self.GLADE_FILE))
        content_area = self.get_content_area()
        content_area.set_spacing(12)
        self.set_border_width(12)
        self.setup_info_bar()
        self._vbox = self._builder.get_object("toplevel-vbox")
        self._vbox.unparent()
        content_area.pack_start(self._vbox, expand=True, fill=True,
                                padding=12)
        self._vbox.pack_start(self._info_bar_container, expand=False,
                              fill=False, padding=0)
        self.liststore = self.make_liststore()
        self.link_use_type_combobox(self.liststore)
        self.link_hosted_service_widgets()
        self.link_local_service_widgets()
        self.setup_buttons()

    def on_combo_changed(self, combobox):
        list_iter = self.liststore.get_iter(combobox.get_active())
        if not self.active_widget is None:
            self._vbox.remove(self.active_widget)
        [management_type] = self.liststore.get(list_iter, 0)
        self.set_button_text(management_type)
        if self._initialised:
            self.controller.management_type = management_type
            self.controller.modify()
        [self.active_widget] = self.liststore.get(list_iter, 2)
        self.active_widget.unparent()
        self._vbox.add(self.active_widget)

    def on_changed_event(self, widget, attribute):
        setattr(self.controller, attribute, widget.get_text())
        self.controller.modify()

    def quit(self, *args):
        self.destroy()

    def revert(self, button):
        self.controller.revert()
        self.load_data()
        # One extra revert to reset after loading data
        self.controller.revert()
