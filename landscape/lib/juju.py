from __future__ import absolute_import

import os
import json
import logging

from landscape.lib.fs import read_text_file


def get_juju_info(config):
    """
    Returns available Juju info or C{None} if the path referenced from
    L{config} is not a valid file.
    """
    if not os.path.exists(config.juju_filename):
        return

    json_contents = read_text_file(config.juju_filename)
    try:
        juju_info = json.loads(json_contents)
    # Catch any error the json lib could throw, because we don't know or
    # care what goes wrong - we'll display a generic error message and
    # return None in any case.
    except Exception:
        logging.exception(
            "Error attempting to read JSON from %s" % config.juju_filename)
        return None

    juju_info["api-addresses"] = juju_info["api-addresses"].split()
    return juju_info
