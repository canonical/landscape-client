"""
Functions for interacting with the snapd REST API.
See https://snapcraft.io/docs/snapd-api for documentation of the API.
"""
import json
import pycurl
from io import BytesIO

SNAPD_SOCKET = "/run/snapd.socket"
BASE_URL = "http://localhost/v2"


class SnapdHttpException(Exception):
    pass


class SnapHttp:
    def __init__(self, snap_url=BASE_URL, snap_socket=SNAPD_SOCKET):
        self._snap_url = snap_url
        self._snap_socket = snap_socket

    def get_snaps(self):
        return self._get("/snaps")

    def _get(self, path):
        if not path.startswith("/"):
            path = "/" + path

        curl = pycurl.Curl()
        buff = BytesIO()

        curl.setopt(curl.UNIX_SOCKET_PATH, self._snap_socket)
        curl.setopt(curl.URL, self._snap_url + path)
        curl.setopt(curl.WRITEDATA, buff)

        try:
            curl.perform()
        except pycurl.error as e:
            raise SnapdHttpException(e)

        response_code = curl.getinfo(curl.RESPONSE_CODE)
        if response_code >= 400:
            raise SnapdHttpException(buff.getvalue())

        return json.loads(buff.getvalue())["result"]
