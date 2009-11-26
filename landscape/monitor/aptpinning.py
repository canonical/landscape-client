import os

from landscape.monitor.monitor import DataWatcher


class AptPinning(DataWatcher):
    """
    Report the system APT pinning configuration.
    """

    persist_name = "apt-pinning"
    message_type = "apt-pinning"
    message_key = "files"
    run_interval = 3600 # 1 hour

    def __init__(self, etc_apt_directory="/etc/apt"):
        self._etc_apt_directory = etc_apt_directory

    def get_data(self):
        """Return a C{dict} mapping APT pinning file names to their content."""
        data = {}

        def read_file(filename):
            fd = open(filename, "r")
            content = fd.read()
            fd.close()
            return content

        preferences_filename = os.path.join(self._etc_apt_directory,
                                            "preferences")
        if os.path.exists(preferences_filename):
            data[preferences_filename] = read_file(preferences_filename)

        preferences_directory = os.path.join(self._etc_apt_directory,
                                            "preferences.d")
        if os.path.isdir(preferences_directory):
            for entry in os.listdir(preferences_directory):
                filename = os.path.join(preferences_directory, entry)
                if os.path.isfile(filename):
                    data[filename] = read_file(filename)

        return data

    def run(self):
        return self.exchange(urgent=True)
