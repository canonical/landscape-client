from gi.repository import Gtk

from landscape.configuration import register
from landscape.ui.model.configuration import LandscapeSettingsConfiguration
from landscape.ui.view.configuration import LandscapeClientSettingsDialog
from landscape.ui.controller.configuration import ConfigController


APPLICATION_ID = "com.canonical.landscape-client.settings.ui"


class LandscapeSettingsApplicationController(Gtk.Application):
    """
    Core application controller for the landscape settings application.
    """

    def __init__(self, data_path=None):
        super(LandscapeSettingsApplicationController, self).__init__(
            application_id=APPLICATION_ID)
        self.data_path = data_path
        self.connect("activate", self.setup_ui)

    def get_config(self):
        return LandscapeSettingsConfiguration([])

    def setup_ui(self, data=None):
        config = self.get_config()
        controller = ConfigController(config)
        self.settings_dialog = LandscapeClientSettingsDialog(
            controller, data_path=self.data_path)
        self.settings_dialog.run()
        # register(config)
