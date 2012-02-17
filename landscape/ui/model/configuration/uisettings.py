from gi.repository import Gio


class ObservableUISettings(object):

    BASE_KEY = "com.canonical.landscape-client-settings"

    def __init__(self, settings):
        self.settings = settings.new(self.BASE_KEY)
        self.settings.connect("changed::is-hosted", self._on_is_hosted_changed)
        self.settings.connect("changed::hosted-landscape-host",
                              self._on_hosted_landscape_host_changed)

    def get_is_hosted(self):
        return self.settings.get_boolean("is-hosted")

    def get_hosted_landscape_host(self):
        return self.settings.get_string("hosted-landscape-host")
    
    def _on_is_hosted_changed(self, settings, key):
        pass

    def _on_hosted_landscape_host_changed(self, settings, key):
        pass

