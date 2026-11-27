"""Shared config mapping used by the snap's configuration hooks."""

import os


def _write_snap_common_file(relative_path: str, content: str, mode: int) -> str:
    """Write `content` to `relative_path` under $SNAP_COMMON with `mode`, and
    return the full path."""
    path = os.path.join(os.getenv("SNAP_COMMON"), relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as f:
        os.fchmod(f.fileno(), mode)  # Also fix the mode of an existing file.
        f.write(content)

    return path


def update_ssl_cert(cert: str) -> str:
    return _write_snap_common_file("etc/ssl/certs/ssl-public-key.crt", cert, 0o644)


def update_ssl_client_cert(cert: str) -> str:
    return _write_snap_common_file("etc/ssl/certs/ssl-client-cert.crt", cert, 0o644)


def update_ssl_client_private_key(key: str) -> str:
    return _write_snap_common_file(
        "etc/ssl/private/ssl-client-private-key.key",
        key,
        0o600,
    )


# Each entry maps a snap config key to a landscape config key,
# with an optional mapping applied to the value on write.
CONFIG_ENTRIES = [
    ("account-name", "account_name", None),
    ("computer-title", "computer_title", None),
    ("url", "url", None),
    ("ping-url", "ping_url", None),
    ("ssl-public-key", "ssl_public_key", update_ssl_cert),
    ("ssl-client-cert", "ssl_client_cert", update_ssl_client_cert),
    (
        "ssl-client-private-key",
        "ssl_client_private_key",
        update_ssl_client_private_key,
    ),
    ("log-level", "log_level", None),
    ("script-users", "script_users", None),
    ("manager-plugins", "manager_plugins", None),
    ("monitor-plugins", "monitor_plugins", None),
    ("access-group", "access_group", None),
    ("registration-key", "registration_key", None),
    ("ping-interval", "ping_interval", None),
    ("urgent-exchange-interval", "urgent_exchange_interval", None),
    ("snap-monitor-interval", "snap_monitor_interval", None),
    ("package-monitor-interval", "package_monitor_interval", None),
    ("flush-interval", "flush_interval", None),
    ("exchange-interval", "exchange_interval", None),
    ("apt-update-interval", "apt_update_interval", None),
    ("apt-update-timeout", "apt_update_timeout", None),
    ("cloud", "cloud", None),
]
