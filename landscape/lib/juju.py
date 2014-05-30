import json
import logging

from glob import glob

from landscape.lib.fs import read_file


def get_juju_info(config):
    """
    Returns the Juju info or C{None} if the path referenced from
    L{config} is not a file or that file isn't valid JSON.
    """
    juju_directory = config.juju_directory

    juju_info_list = []

    for juju_file in glob("%s/*.json" % juju_directory):

        if juju_file.endswith(".json"):
            json_contents = read_file(juju_file)
            try:
                juju_info = json.loads(json_contents)
            except Exception:
                logging.exception(
                    "Error attempting to read JSON from %s" % juju_file)
                return None
            else:
                if "api-addresses" in juju_info:
                    juju_info["api-addresses"] = juju_info["api-addresses"].split()
                juju_info_list.append(juju_info)

    return juju_info_list or None
