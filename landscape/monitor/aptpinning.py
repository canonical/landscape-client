import os

from landscape.monitor.monitor import DataWatcher


class AptPinning(DataWatcher):
    """
    Report whether the system uses APT pinning.
    """

    persist_name = "apt-pinning"
    message_type = "apt-pinning"
    message_key = "status"
    run_interval = 3600 # 1 hour

    def __init__(self, etc_apt_directory="/etc/apt"):
        self._etc_apt_directory = etc_apt_directory

    def get_data(self):
        """Return a boolean indicating whether the computer needs a reboot."""

        def join_etc_apt(path):
            return os.path.join(self._etc_apt_directory, path)


        if os.path.exists(join_etc_apt("preferences")):
            return True

        preferences_directory = join_etc_apt("preferences.d")
        if not os.path.exists(preferences_directory):
            return False
        for filename in os.listdir(preferences_directory):
            if os.path.isfile(os.path.join(preferences_directory, filename)):
                return True
        return False

    def run(self):
        return self.exchange(urgent=True)
