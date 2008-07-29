from landscape.lib.twisted_util import gather_results
from landscape.plugin import PluginRegistry


class SysInfoPluginRegistry(PluginRegistry):

    def __init__(self):
        super(SysInfoPluginRegistry, self).__init__()
        self._headers = []
        self._notes = []

    def add_header(self, name, value):
        """Add a new information header to be displayed to the user."""
        self._headers.append((name, value))

    def get_headers(self):
        """Get all information headers to be displayed to the user."""
        return self._headers

    def add_note(self, note):
        """Add a new eventual note to be shown up to the administrator."""
        self._notes.append(note)

    def get_notes(self):
        """Get all eventual notes to be shown up to the administrator."""
        return self._notes

    def run(self):
        deferreds = []
        for plugin in self.get_plugins():
            deferreds.append(plugin.run())
        return gather_results(deferreds)
