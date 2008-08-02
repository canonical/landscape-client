import os

class ProcessError(Exception):
    """ Error running a process with os.system. """

class SysVConfig(object):

    def __init__(self, filename="/etc/default/landscape-client"):
        self._filename = filename

    def set_start_on_boot(self, flag):
        current = self._parse_file()
        current["RUN"] = flag and 1 or 0
        self._write_file(current)

    def start_landscape(self):
        if os.system("/etc/init.d/landscape-client start"):
            raise ProcessError("Could not start client")

    def stop_landscape(self):
        if os.system("/etc/init.d/landscape-client stop"):
            raise ProcessError("Could not stop client")

    def is_configured_to_run(self):
        state = self._parse_file()
        return bool(state.get("RUN", None))

    def _parse_file(self):
        values = {}
        # Only attempt to parse the file if it exists.
        if os.path.isfile(self._filename):
            for line in open(self._filename, "r"):
                line = line.strip()
                key, value = line.split("=")
                values[key] = value
        return values

    def _write_file(self, values):
        file = open(self._filename, "w")
        for key in sorted(values.keys()):
            file.write("%s=%s\n" % (key, str(values[key])))
        file.close()
