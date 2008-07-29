from landscape.lib.twisted_util import gather_results
from landscape.plugin import PluginRegistry


class SysInfoPluginRegistry(PluginRegistry):
    """
    When the sysinfo plugin registry is run, it will run each of the
    registered plugins so that they get a chance to feed information
    into the registry.
    
    There are three kinds of details collected: headers, notes, and footnotes.

    They are presented to the user in a way similar to the following:

        Header1: Value1   Header3: Value3
        Header2: Value2   Header4: Value4

        => This is first note
        => This is the second note

        The first footnote.
        The second footnote.

    Headers are supposed to display information which is regularly
    available, such as the load and temperature of the system.  Notes
    contain eventual information, such as warnings of high temperatures,
    and low disk space.  Finally, footnotes contain pointers to further
    information such as URLs.
    """

    def __init__(self):
        super(SysInfoPluginRegistry, self).__init__()
        self._headers = []
        self._notes = []
        self._footnotes = []

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

    def add_footnote(self, note):
        """Add a new footnote to be shown up to the administrator."""
        self._footnotes.append(note)

    def get_footnotes(self):
        """Get all footnotes to be shown up to the administrator."""
        return self._footnotes

    def run(self):
        """Run all plugins, and return a deferred aggregating their results.
 
        This will call the run() method on each of the registered plugins,
        and return a deferred which aggregates each resulting deferred.
        """
        deferreds = []
        for plugin in self.get_plugins():
            deferreds.append(plugin.run())
        return gather_results(deferreds)


# def format_output(headers, notes, footer):
#    pass
