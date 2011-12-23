import os

from gi.repository import Gtk


class LandscapeClientSettingsDialog(Gtk.Dialog):

    GLADE_FILE = "landscape-client-settings.glade"
    
    def __init__(self, controller, *args, **kwargs):
        super(LandscapeClientSettingsDialog, self).__init__(*args, **kwargs)
        self.controller = controller
        self.__ui_path = os.path.join(controller.data_path, "ui",
                                      LandscapeClientSettingsDialog.GLADE_FILE)
                                      
        self.__builder = Gtk.Builder()
        self.__builder.add_from_file(self.__ui_path)
        self.__setup_ui()
        
    def __setup_ui(self):
        content_area = self.get_content_area()
        vbox = self.__builder.get_object(
            "landscape-client-settings-dialog-vbox")
        vbox.unparent()
        content_area.pack_start(vbox, expand=True, fill=True, padding=0)
        
        
        

