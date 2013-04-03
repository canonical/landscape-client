"""Programmatically manage the Landscape client SysV-style init script."""

import os


class ProcessError(Exception):
    """ Error running a process with os.system. """


class SysVConfig(object):
    """Configure and drive the Landscape client init script.

    @param filename: Path to the file holding init scripts env variables.
    """

    def __init__(self, filename="/etc/default/landscape-client"):
        self._filename = filename

    def set_start_on_boot(self, flag):
        """Make the init script decide to start the client when it's run."""
        current = self._parse_file()
        current["RUN"] = flag and 1 or 0
        self._write_file(current)

    def restart_landscape(self):
        """Restart the Landscape client service."""
        if os.system("/etc/init.d/landscape-client restart"):
            raise ProcessError("Could not restart client")

    def stop_landscape(self):
        """Stop the Landscape client service."""
        if os.system("/etc/init.d/landscape-client stop"):
            raise ProcessError("Could not stop client")

    def is_configured_to_run(self):
        """
        Return a boolean representing whether the init script will decide to
        actually start the client when it is run.  This method should match
        the semantics of the checks in debian/landscape-client.init.
        """
        state = self._parse_file()
        run_value = state.get("RUN", "0")
        return (not run_value[:1].isspace()) and run_value != "0"

    def _parse_file(self):
        values = {}
        # Only attempt to parse the file if it exists.
        if os.path.isfile(self._filename):
            for line in open(self._filename, "r"):
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=")
                    values[key] = value
        return values

    def _write_file(self, values):
        file = open(self._filename, "w")
        for key in sorted(values.keys()):
            file.write("%s=%s\n" % (key, str(values[key])))
        file.close()
