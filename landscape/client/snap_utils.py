import yaml

from landscape.client import snap_http
from landscape.client.snap_http import SnapdHttpException


def get_assertions(assertion_type: str):
    """Get and parse assertions."""
    try:
        response = snap_http.get_assertions(assertion_type)
    except SnapdHttpException:
        return

    # the snapd API returns multiple assertions as a stream of
    # bytes separated by double newlines, something like this:
    # <assertion1-headers>: <value>
    # <assertion1-headers>: <value>
    #
    # signature
    #
    # <assertion2-headers>: <value>
    # <assertion2-headers>: <value>
    #
    # signature

    # extract the assertion headers + their signatures as separate assertions
    assertions = []
    result = response.result.decode()
    if result:
        sections = result.split("\n\n")
        rest = sections
        while rest:
            headers, signature, *rest = rest
            assertion = yaml.safe_load(headers)
            assertion["signature"] = signature
            assertions.append(assertion)

    return assertions
