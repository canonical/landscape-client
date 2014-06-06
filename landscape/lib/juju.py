import json
import logging
import os.path

from landscape.lib.fs import read_file


def get_juju_info(config):
    """
    Returns the Juju info or C{None} if the path referenced from
    L{config} is not a file or that file isn't valid JSON.
    """
    juju_filename = config.juju_filename
    if not os.path.isfile(juju_filename):
        return None
    json_contents = read_file(juju_filename)
    try:
        juju_info = json.loads(json_contents)
    except Exception:
        logging.exception(
            "Error attempting to read JSON from %s" % juju_filename)
        return None
    else:
        if "api-addresses" in juju_info:
            juju_info["api-addresses"] = juju_info["api-addresses"].split()
        return juju_info
