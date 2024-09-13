import json
import logging
import subprocess
import traceback
import yaml

from landscape.client.manager.plugin import DataWatcherManager


class LivePatch(DataWatcherManager):
    """
    Plugin that captures and reports Livepatch status information
    information.
    """

    message_type = "livepatch"
    message_key = message_type
    persist_name = message_type
    scope = "livepatch"
    run_immediately = True
    run_interval = 1800  # Every 30 min

    def get_data(self):
        json_output = get_livepatch_status("json")
        readable_output = get_livepatch_status("humane")
        return json.dumps(
            {"humane": readable_output, "json": json_output}, sort_keys=True
        )  # Prevent randomness for cache


def _parse_humane(output):
    entries = output.splitlines()
    data = {}

    for entry in entries:
        line = entry.strip()
        if line == "":
            continue
        elif ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().strip('"').strip("'")
            value = value.strip().strip('"').strip("'")
            data[key] = value
        else:
            raise yaml.YAMLError(
                "Input is not a list of key/value pairs: " + output
            )

    return data


def get_livepatch_status(format_type):
    """
    Livepatch returns output formatted either 'json' or 'humane' (human-
    readable yaml). This function takes the the output and parses it into a
    python dictionary and sticks it in "output" along with error and return
    code information.
    """

    data = {}
    try:
        completed_process = subprocess.run(
            ["canonical-livepatch", "status", "--format", format_type],
            encoding="utf8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        data["return_code"] = -1
        data["error"] = str(exc)
        data["output"] = ""
    except Exception as exc:
        data["return_code"] = -2
        data["error"] = str(exc)
        data["output"] = ""
        logging.error(traceback.format_exc())
    else:
        output = completed_process.stdout.strip()
        try:
            if output:  # We don't want to parse an empty string
                if format_type == "json":
                    output = json.loads(output)
                    if "Last-Check" in output:  # Remove timestamps for cache
                        del output["Last-Check"]
                    if "Uptime" in output:
                        del output["Uptime"]
                else:
                    output = _parse_humane(output)
                    if "last check" in output:
                        del output["last check"]
            data["return_code"] = completed_process.returncode
            data["error"] = completed_process.stderr
            data["output"] = output
        except (yaml.YAMLError, json.decoder.JSONDecodeError) as exc:
            data["return_code"] = completed_process.returncode
            data["error"] = str(exc)
            data["output"] = output

    return data
