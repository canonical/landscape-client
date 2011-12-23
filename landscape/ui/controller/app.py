from gi.repository import Gtk, Gio


APPLICATION_ID="com.canonical.landscape-client.settings.ui"


class LandscapeSettingsApplicationController(Gtk.Application):
    """
    Core application controller for the landscape settings application.
    """


    def __init__(self):
        super(LandscapeSettingsApplicationController, self).__init__(
            application_id=APPLICATION_ID)
        self.connect("activate", self.setup_ui)


    def setup_ui(self):
        pass
