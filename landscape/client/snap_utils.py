from copy import deepcopy

import yaml

from landscape.client import snap_http
from landscape.client.snap_http import SnapdHttpException


class IgnoreYamlAliasesLoader(yaml.SafeLoader):
    """Patch `yaml.SafeLoader` to ignore aliases like *alias when loading.

    For instance, a system-user assertion can have the following json:
      {
          [...]
           "system-user-authority": "*",
          [...]
      }
    which after signing gets converted to yaml that looks like:
      [...]
      system-user-authority: *
      [...]
    pyyaml tries to parse the * as the start of an alias leading to errors.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.yaml_implicit_resolvers = deepcopy(
            super().yaml_implicit_resolvers,
        )
        self.yaml_implicit_resolvers.pop("*", None)

    def fetch_alias(self):
        return super().fetch_plain()


def parse_assertion(headers, signature):
    """Parse an assertion."""
    assertion = yaml.load(headers, IgnoreYamlAliasesLoader)
    assertion["signature"] = signature
    return assertion


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
    if not isinstance(response.result, bytes):
        return

    assertions = []

    result = response.result.decode()
    if result:
        sections = result.split("\n\n")
        rest = sections
        while rest:
            headers, signature, *rest = rest
            parsed = parse_assertion(headers, signature)
            assertions.append(parsed)

    return assertions


def get_snap_info():
    """Get the snap device information."""
    info = {}

    serial_as = get_assertions("serial")
    if serial_as:
        info["serial"] = serial_as[0]["serial"]
        info["model"] = serial_as[0]["model"]
        info["brand"] = serial_as[0]["brand-id"]

    return info
