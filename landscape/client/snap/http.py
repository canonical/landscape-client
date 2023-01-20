"""
Functions for interacting with the snapd REST API.
See https://snapcraft.io/docs/snapd-api for documentation of the API.
"""
import json
from io import BytesIO

import pycurl

SNAPD_SOCKET = "/run/snapd.socket"
BASE_URL = "http://localhost/v2"

# For the below, refer to https://snapcraft.io/docs/snapd-api#heading--changes
COMPLETE_STATUSES = {"Done", "Error", "Hold", "Abort"}
INCOMPLETE_STATUSES = {"Do", "Doing", "Undo", "Undoing"}
SUCCESS_STATUSES = {"Done"}
ERROR_STATUSES = {"Error", "Hold", "Unknown"}


class SnapdHttpException(Exception):
    @property
    def json(self):
        """Attempts to parse the body of this exception as json."""
        body = self.args[0]

        return json.loads(body)


class SnapHttp:
    def __init__(self, snap_url=BASE_URL, snap_socket=SNAPD_SOCKET):
        self._snap_url = snap_url
        self._snap_socket = snap_socket

    def check_change(self, cid):
        """Check the status of snapd change with id `cid`."""
        return self._get("/changes/" + cid)

    def check_changes(self):
        """Check the status of all snapd changes."""
        return self._get("/changes?select=all")

    def enable_snap(self, name):
        """Enables a previously disabled snap by `name`."""
        return self._post("/snaps/" + name, {"action": "enable"})

    def enable_snaps(self, snaps):
        """See `self.enable_snap`."""
        return self._post(
            "/snaps",
            {
                "action": "enable",
                "snaps": snaps,
            },
        )

    def disable_snap(self, name):
        """
        Disables a snap by `name`, making its binaries and services
        unavailable.
        """
        return self._post("/snaps/" + name, {"action": "disable"})

    def disable_snaps(self, snaps):
        """See `self.disable_snap`."""
        return self._post(
            "/snaps",
            {
                "action": "enable",
                "snaps": snaps,
            },
        )

    def get_snaps(self):
        """GETs a list of installed snaps."""
        return self._get("/snaps")

    def hold_snap(self, name, hold_level="general", time="forever"):
        """
        Holds a snap by `name` at `hold_level` until `time`.

        `hold_level` is "general" or "auto-refresh".
        `time` is "forever" or an RFC3339 timestamp.
        """
        body = _clean_dict(
            {
                "action": "hold",
                "hold-level": hold_level,
                "time": time,
            },
        )

        return self._post("/snaps/" + name, body)

    def hold_snaps(self, snaps, hold_level="general", time="forever"):
        """
        Same as `self.hold_snap`, except for a batch of snaps.
        """
        body = _clean_dict(
            {
                "action": "hold",
                "snaps": snaps,
                "hold-level": hold_level,
                "time": time,
            },
        )

        return self._post("/snaps", body)

    def install_snap(self, name, revision=None, channel=None, classic=False):
        """
        Installs a snap by `name` at `revision`, tracking `channel`. If
        `classic`, then snap is installed in classic containment mode.

        If `revision` is not provided, latest will be used.
        If `channel` is not provided, stable will be used.
        """
        body = _clean_dict(
            {
                "action": "install",
                "revision": revision,
                "channel": channel,
                "classic": classic,
            },
        )

        return self._post("/snaps/" + name, body)

    def install_snaps(self, snaps):
        return self._post("/snaps", {"action": "install", "snaps": snaps})

    def refresh_snap(self, name, revision=None, channel=None, classic=None):
        """
        Refreshes a snap, switching to the given `revision` and `channel` if
        provided.

        If `classic` is provided, snap will be changed to the classic
        confinement if True, or out of classic confinement if False.
        """
        body = _clean_dict(
            {
                "action": "refresh",
                "revision": revision,
                "channel": channel,
                "classic": classic,
            },
        )

        return self._post("/snaps/" + name, body)

    def refresh_snaps(self, snaps=[]):
        """
        Refreshes `snaps` to the latest revision. If `snaps` is empty,
        all snaps are refreshed.
        """
        body = {"action": "refresh"}

        if snaps:
            body["snaps"] = snaps

        return self._post("/snaps", body)

    def revert_snap(self, name, revision=None, classic=None):
        """
        Reverts a snap, switching to the given `revision` is provided.
        Otherwise switches to the revision used prior to the last
        refresh.

        If `classic` is provided, snap will be changed to classic
        confinement if True, or out of classic confinement if False.
        """
        body = _clean_dict(
            {
                "action": "revert",
                "revision": revision,
                "classic": classic,
            },
        )

        return self._post("/snaps/" + name, body)

    def revert_snaps(self, snaps):
        """
        Reverts `snaps` to the revision used prior to the last refresh.
        """
        return self._post(
            "/snaps",
            {
                "action": "refresh",
                "snaps": snaps,
            },
        )

    def remove_snap(self, name):
        return self._post("/snaps/" + name, {"action": "remove"})

    def remove_snaps(self, snaps):
        return self._post(
            "/snaps",
            {
                "action": "remove",
                "snaps": snaps,
            },
        )

    def switch_snap(self, name, channel="stable"):
        """Switches the channel that a snap is tracking."""
        return self._post(
            "/snaps/" + name,
            _clean_dict(
                {
                    "action": "switch",
                    "channel": channel,
                },
            ),
        )

    def switch_snaps(self, snaps, channel="stable"):
        return self._post(
            "/snaps",
            _clean_dict(
                {
                    "action": "switch",
                    "snaps": snaps,
                    "channel": channel,
                },
            ),
        )

    def unhold_snap(self, name):
        """
        Remove a hold on a snap, allowing it to refresh on it's usual
        schedule.
        """
        return self._post("/snaps/" + name, {"action": "unhold"})

    def unhold_snaps(self, snaps):
        """See `self.unhold_snap`."""
        return self._post(
            "/snaps",
            {
                "action": "unhold",
                "snaps": snaps,
            },
        )

    def _get(self, path):
        """Perform a GET request of `path` to the snap REST API."""
        curl, buff = self._setup_curl(path)

        self._perform(curl, buff)

        return json.loads(buff.getvalue())

    def _perform(self, curl, buff, raise_on_error=True):
        """
        Performs a pycurl request, optionally raising on a pycurl or HTTP
        error.
        """
        try:
            curl.perform()
        except pycurl.error as e:
            raise SnapdHttpException(e)

        response_code = curl.getinfo(curl.RESPONSE_CODE)
        if response_code >= 400:
            raise SnapdHttpException(buff.getvalue())

    def _post(self, path, body):
        """
        Perform a POST request of `path` to the snap REST API, with the
        JSON-ified `body`
        """
        curl, buff = self._setup_curl(path)
        json_body = json.dumps(body)

        curl.setopt(curl.POSTFIELDS, json_body)
        curl.setopt(curl.HTTPHEADER, ["Content-Type: application/json"])
        self._perform(curl, buff)

        return json.loads(buff.getvalue())

    def _setup_curl(self, path):
        """
        Prepares pycurl to communicate with the snap REST API at the given
        `path`.
        """
        curl = pycurl.Curl()
        buff = BytesIO()

        curl.setopt(curl.UNIX_SOCKET_PATH, self._snap_socket)
        curl.setopt(curl.URL, self._snap_url + path)
        curl.setopt(curl.WRITEDATA, buff)

        return curl, buff


def _clean_dict(d):
    """
    Only includes keys from `d` in the resulting dict if they are not
    None.
    """
    return {k: v for k, v in d.items() if v is not None}
