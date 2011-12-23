from gi.repository import Gtk


class LandscapeClientSettingsDialog(Gtk.Dialog):
    
    def __init__(self, controller, *args, **kwargs):
        super(LandscapeClientSettingsDialog, self).__init__(*args, **kwargs)
        self.controller = controller
