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


def get_snaps():
    return _get("/snaps")


def _get(path):
    if not path.startswith("/"):
        path = "/" + path

    curl = pycurl.Curl()
    buff = BytesIO()

    curl.setopt(curl.UNIX_SOCKET_PATH, SNAPD_SOCKET)
    curl.setopt(curl.URL, BASE_URL + path)
    curl.setopt(curl.WRITEDATA, buff)

    curl.perform()

    response_code = curl.getinfo(curl.RESPONSE_CODE)
    if response_code >= 400:
        raise SnapdHttpException(buff.getvalue())

    return json.loads(buff.getvalue())
