import os

from landscape.lib.fs import read_file
from landscape.constants import APT_PREFERENCES_SIZE_LIMIT

from landscape.monitor.plugin import DataWatcher


class AptPreferences(DataWatcher):
    """
    Report the system APT preferences configuration.
    """

    persist_name = "apt-preferences"
    message_type = "apt-preferences"
    message_key = "data"
    run_interval = 900  # 15 minutes
    scope = "package"
    size_limit = APT_PREFERENCES_SIZE_LIMIT

    def __init__(self, etc_apt_directory="/etc/apt"):
        self._etc_apt_directory = etc_apt_directory

    def get_data(self):
        """Return a C{dict} mapping APT preferences files to their contents.

        If no APT preferences configuration is set at all on the system, then
        simply return C{None}
        """
        data = {}
        read_unicode = lambda filename: unicode(read_file(filename))
        preferences_filename = os.path.join(self._etc_apt_directory,
                                            u"preferences")
        if os.path.exists(preferences_filename):
            data[preferences_filename] = read_unicode(preferences_filename)

        preferences_directory = os.path.join(self._etc_apt_directory,
                                             u"preferences.d")
        if os.path.isdir(preferences_directory):
            for entry in os.listdir(preferences_directory):
                filename = os.path.join(preferences_directory, entry)
                if os.path.isfile(filename):
                    data[filename] = read_unicode(filename)

        if data == {}:
            return None

        item_size_limit = self.size_limit / len(data.keys())
        for filename, contents in data.iteritems():
            if len(filename) + len(contents) > item_size_limit:
                truncated_contents_size = item_size_limit - len(filename)
                data[filename] = data[filename][0:truncated_contents_size]

        return data

    def run(self):
        return self.exchange(urgent=True)
