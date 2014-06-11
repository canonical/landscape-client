import os
import json
import logging

from glob import glob

from landscape.lib.fs import read_file


def get_juju_info(config):
    """
    Returns the list of Juju info or C{None} if the path referenced from
    L{config} is not a valid directory.

    The list of juju info is constructed by appending all the contents of
    *.json files found in the path referenced from the L{config}.
    """
    juju_directory = config.juju_directory
    legacy_juju_file = config.juju_filename

    juju_info_list = []
    juju_file_list = glob("%s/*.json" % juju_directory)

    if os.path.exists(legacy_juju_file):
        juju_file_list.append(legacy_juju_file)

    for juju_file in juju_file_list:

        json_contents = read_file(juju_file)
        try:
            juju_info = json.loads(json_contents)
        # Catch any error the json lib could throw, because we don't know or
        # care what goes wrong - we'll display a generic error message and
        # return None in any case.
        except Exception:
            logging.exception(
                "Error attempting to read JSON from %s" % juju_file)
            return None
        else:
            if "api-addresses" in juju_info:
                split = juju_info["api-addresses"].split()
                juju_info["api-addresses"] = split
            juju_info_list.append(juju_info)

    juju_info_list.sort(key=lambda x: x["unit-name"])
    return juju_info_list or None
