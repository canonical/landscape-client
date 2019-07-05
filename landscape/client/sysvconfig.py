"""Programmatically manage the Landscape client SysV-style init script."""
from subprocess import Popen


class ProcessError(Exception):
    """ Error running a process with os.system. """


class SystemdConfig(object):
    """Configure and drive the Landscape client service."""

    def set_start_on_boot(self, flag):
        """Make the service decide to start the client when it's run."""
        action = "enable" if flag else "disable"
        cmd = ["systemctl", action, "landscape-client.service"]
        Popen(cmd).wait()

    def restart_landscape(self):
        """Restart the Landscape client service."""
        cmd = ["systemctl", "restart", "landscape-client.service"]
        if Popen(cmd).wait():
            raise ProcessError("Could not restart client")

    def stop_landscape(self):
        """Stop the Landscape client service."""
        if Popen(["systemctl", "stop", "landscape-client.service"]).wait():
            raise ProcessError("Could not stop client")

    def is_configured_to_run(self):
        """
        Return a boolean representing whether the service will start on boot.
        """
        cmd = ["systemctl", "is-enabled", "landscape-client.service"]
        return Popen(cmd).wait() == 0


# Deprecated alias for charms and scripts still using the old name.
SysVConfig = SystemdConfig
