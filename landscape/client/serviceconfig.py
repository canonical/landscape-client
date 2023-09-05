"""Interface for interacting with service managers managing landscape-client.

This module exports a single class, `ServiceConfig`, which is aliased to a
concrete implementation based on configuration. Concrete implementations
provide the following interface:

set_start_on_boot(flag: bool) -> None
restart_landscape() -> None
stop_landscape() -> None
is_configured_to_run() -> bool

Methods should raise `ServiceConfigException` if necessary.
"""
import os
import subprocess

SERVICE_NAME = "landscape-client"
SYSTEMD_SERVICE = f"{SERVICE_NAME}.service"

SNAPCTL = "/usr/bin/snapctl"
SYSTEMCTL = "systemctl"  # Cannot hardcode here as bionic is in different path


class ServiceConfigException(Exception):
    """
    Error modifying the landscape-client service's status or configuration.
    """


class SystemdConfig:
    """
    A collection of methods for driving the landscape-client systemd service.
    """

    @staticmethod
    def set_start_on_boot(flag: bool) -> None:
        action = "enable" if flag else "disable"
        SystemdConfig._call_systemctl(action)

    @staticmethod
    def restart_landscape() -> None:
        try:
            SystemdConfig._call_systemctl("restart", check=True)
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not restart {SERVICE_NAME}")

    @staticmethod
    def stop_landscape() -> None:
        try:
            SystemdConfig._call_systemctl("stop", check=True)
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not stop {SERVICE_NAME}")

    @staticmethod
    def is_configured_to_run() -> bool:
        completed_process = SystemdConfig._call_systemctl("is-enabled")
        return completed_process.returncode == 0

    @staticmethod
    def _call_systemctl(
        action: str,
        **run_kwargs,
    ) -> subprocess.CompletedProcess:
        """Calls systemctl, passing `action` and `run_kwargs`, while consuming
        stdout.
        """
        return subprocess.run(
            [SYSTEMCTL, action, SYSTEMD_SERVICE, "--quiet"],
            stdout=subprocess.PIPE,
            **run_kwargs,
        )


class SnapdConfig:
    """
    A collection of methods for driving the landscape-client snapd service.
    """

    @staticmethod
    def set_start_on_boot(flag: bool) -> None:
        if flag:
            cmd = "start"
            param = "--enable"
        else:
            cmd = "stop"
            param = "--disable"

        SnapdConfig._call_snapctl(cmd, param)

    @staticmethod
    def restart_landscape() -> None:
        try:
            SnapdConfig._call_snapctl("restart", check=True)
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not restart {SERVICE_NAME}")

    @staticmethod
    def stop_landscape() -> None:
        try:
            SnapdConfig._call_snapctl("stop", check=True)
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not stop {SERVICE_NAME}")

    @staticmethod
    def is_configured_to_run() -> bool:
        completed_process = SnapdConfig._call_snapctl("services", text=True)
        stdout = completed_process.stdout

        return stdout and "enabled" in stdout

    @staticmethod
    def _call_snapctl(
        action: str,
        *cmd_args,
        **run_kwargs,
    ) -> subprocess.CompletedProcess:
        """Calls snapctl, passing `action`, `cmd_args`, and `run_kwargs`, while
        consuming stdout.
        """
        return subprocess.run(
            [SNAPCTL, action, SERVICE_NAME, *cmd_args],
            stdout=subprocess.PIPE,
            **run_kwargs,
        )


if os.environ.get("SNAP_REVISION"):
    ServiceConfig = SnapdConfig
else:
    ServiceConfig = SystemdConfig
