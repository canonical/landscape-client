from gi.repository import Gtk

from landscape.configuration import LandscapeSetupConfiguration
from landscape.ui.view.configuration import ClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController


APPLICATION_ID = "com.canonical.landscape-client.settings.ui"


class SettingsApplicationController(Gtk.Application):
    """
    Core application controller for the landscape settings application.
    """

    def __init__(self, data_path=None):
        super(SettingsApplicationController, self).__init__(
            application_id=APPLICATION_ID)
        self.data_path = data_path
        self.connect("activate", self.setup_ui)

    def get_config(self):
        return LandscapeSetupConfiguration()

    def setup_ui(self, data=None):
        config = self.get_config()
        controller = ConfigController(config)
        self.settings_dialog = ClientSettingsDialog(controller,
                                                    data_path=self.data_path)
        self.settings_dialog.run()
