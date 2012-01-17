from gi.repository import Gtk

from landscape.ui.model.configuration.proxy import ConfigurationProxy
from landscape.ui.view.configuration import ClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController


APPLICATION_ID = "com.canonical.landscape-client.settings.ui"


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

    def setup_ui(self, data=None):
        config = self.get_config()
        controller = ConfigController(config, args=self._args)
        controller.load()
        self.settings_dialog = ClientSettingsDialog(controller)
        self.settings_dialog.run()
