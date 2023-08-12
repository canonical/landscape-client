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
SYSTEMCTL = "/usr/bin/systemctl"


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
        subprocess.run(
            [SYSTEMCTL, action, SYSTEMD_SERVICE],
            stdout=subprocess.PIPE,
        )

    @staticmethod
    def restart_landscape() -> None:
        try:
            subprocess.run(
                [SYSTEMCTL, "restart", SYSTEMD_SERVICE],
                check=True,
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not restart {SERVICE_NAME}")

    @staticmethod
    def stop_landscape() -> None:
        try:
            subprocess.run(
                [SYSTEMCTL, "stop", SYSTEMD_SERVICE],
                check=True,
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not stop {SERVICE_NAME}")

    @staticmethod
    def is_configured_to_run() -> bool:
        completed_process = subprocess.run(
            [SYSTEMCTL, "is-enabled", SYSTEMD_SERVICE],
            stdout=subprocess.PIPE,
        )
        return completed_process.returncode == 0


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

        subprocess.run(
            [SNAPCTL, cmd, SERVICE_NAME, param],
            stdout=subprocess.PIPE,
        )

    @staticmethod
    def restart_landscape() -> None:
        try:
            subprocess.run(
                [SNAPCTL, "restart", SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not restart {SERVICE_NAME}")

    @staticmethod
    def stop_landscape() -> None:
        try:
            subprocess.run(
                [SNAPCTL, "stop", SERVICE_NAME],
                check=True,
                stdout=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            raise ServiceConfigException(f"Could not stop {SERVICE_NAME}")

    @staticmethod
    def is_configured_to_run() -> bool:
        completed_process = subprocess.run(
            [SNAPCTL, "services", SERVICE_NAME],
            stdout=subprocess.PIPE,
        )
        stdout = completed_process.stdout

        return stdout and "enabled" in stdout


if os.environ.get("SNAP_REVISION"):
    ServiceConfig = SnapdConfig
else:
    ServiceConfig = SystemdConfig
