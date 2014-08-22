import os
import json
import logging

from glob import glob

from landscape.lib.fs import read_file


def get_juju_info(config):
    """
    Returns available Juju info or C{None} if the path referenced from
    L{config} is not a valid directory.

    XXX At the moment this function returns a 2-tuple because we're
    transitioning from unit-computer associations to machine-computer
    associations. Once the transition is completed in the server, the
    old format can be dropped.

    The list of old juju info is constructed by appending all the contents of
    *.json files found in the path referenced from the L{config}.
    """
    juju_directory = config.juju_directory
    legacy_juju_file = config.juju_filename

    new_juju_info = {}
    juju_info_list = []
    juju_file_list = glob("%s/*.json" % juju_directory)

    if os.path.exists(legacy_juju_file):
        juju_file_list.append(legacy_juju_file)

    for index, juju_file in enumerate(juju_file_list):

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

        if "api-addresses" in juju_info:
            split = juju_info["api-addresses"].split()
            juju_info["api-addresses"] = split

        # Strip away machine-id, which is not understood by the old format
        machine_id = juju_info.pop("machine-id", None)

        if index == 0 and machine_id is not None:
            # We care only about the first file, as the machine ID is the same
            # for all
            new_juju_info["environment-uuid"] = juju_info["environment-uuid"]
            new_juju_info["api-addresses"] = juju_info["api-addresses"]
            new_juju_info["machine-id"] = machine_id

        juju_info_list.append(juju_info)

    juju_info_list.sort(key=lambda x: x["unit-name"])

    if juju_info_list:
        return juju_info_list, new_juju_info
    return None
