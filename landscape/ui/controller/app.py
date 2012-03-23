import sys

from gettext import gettext as _

from gi.repository import Gio, Gtk, Notify

from landscape.ui.model.configuration.proxy import ConfigurationProxy
from landscape.ui.model.configuration.state import ConfigurationModel
from landscape.ui.model.configuration.uisettings import UISettings
from landscape.ui.view.configuration import ClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController


APPLICATION_ID = "com.canonical.landscape-client.settings.ui"
NOTIFY_ID = "Landscape management service"


class SettingsApplicationController(Gtk.Application):
    """
    Core application controller for the landscape settings application.
    """

    def __init__(self, args=[]):
        super(SettingsApplicationController, self).__init__(
            application_id=APPLICATION_ID)
        self._args = args
        self.connect("activate", self.setup_ui)

    def get_config(self):
        return ConfigurationProxy()

    def get_uisettings(self):
        return UISettings(Gio.Settings)

    def on_notify(self, message):
        notification = Notify.Notification.new(NOTIFY_ID, message,
                                               "dialog-information")
        notification.show()

    def on_error(self, message):
        notification = Notify.Notification.new(NOTIFY_ID, message,
                                               "dialog-information")
        notification.show()

    def on_succeed(self, action=None):
        if action:
            message = action
        else:
            message = _("Success.")
        notification = Notify.Notification.new(NOTIFY_ID, message,
                                               "dialog-information")
        notification.show()

    def on_fail(self, action=None):
        if action:
            message = action
        else:
            message = _("Failure.")
        notification = Notify.Notification.new(NOTIFY_ID, message,
                                               "dialog-information")
        notification.show()

    def setup_ui(self, data=None, asynchronous=True):
        """
        L{setup_ui} wires the model to the L{ConfigurationController} and then
        invokes the view with the controller.  When the dialog exits
        appropriate termination is triggered.

        @param data: the Gtk callback could pass this, but it is always None in
        practice.
        @param asynchronous: a parameter passed through to
        L{ConfigurationController.exit}, it indicates whether the exit method
        should be called asynchronously.  Is makes testing easier to use it
        synchronously.
        """
        Notify.init(NOTIFY_ID)
        config = self.get_config()
        uisettings = self.get_uisettings()
        model = ConfigurationModel(proxy=config, proxy_loadargs=self._args,
                                   uisettings=uisettings)
        controller = ConfigController(model)
        if controller.load():
            self.settings_dialog = ClientSettingsDialog(controller)
            if self.settings_dialog.run() == Gtk.ResponseType.OK:
                controller.persist(self.on_notify, self.on_error,
                                   self.on_succeed, self.on_fail)
            controller.exit(asynchronous=asynchronous)
            self.settings_dialog.destroy()
        else:
            self.on_fail(action=_("Authentication failed"))
            sys.stderr.write("Authentication failed.\n")
