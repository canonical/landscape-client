import json
import subprocess
from typing import Any

from landscape.client.manager.plugin import DataWatcherManager


class CloudInit(DataWatcherManager):

    message_type = "cloud-init"
    message_key = message_type
    scope = "cloud-init"
    persist_name = message_type
    run_immediately = True
    run_interval = 3600 * 24  # 24h

    def get_data(self) -> str:
        return json.dumps(get_cloud_init(), sort_keys=True)


def get_cloud_init() -> dict[str, Any]:
    """
    cloud-init returns all the information the instance has been initialized
    with, in JSON format. This function takes the the output and parses it
    into a python dictionary and sticks it in "output" along with error and
    return code information.
    """

    data: dict[str, Any] = {}
    output: dict[str, Any] = {}

    try:
        completed_process = subprocess.run(
            ["cloud-init", "query", "-a"],
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
    else:
        string_output = completed_process.stdout.strip()
        try:
            # INFO: We don't want to parse an empty string.
            if string_output:
                json_output = json.loads(string_output)
                # INFO: Only return relevant information from cloud init.
                output["availability_zone"] = json_output.get(
                    "availability_zone",
                    "",
                ) or json_output.get("availability-zone", "")
            data["return_code"] = completed_process.returncode
            data["error"] = completed_process.stderr
            data["output"] = output
        except json.decoder.JSONDecodeError as exc:
            data["return_code"] = completed_process.returncode
            data["error"] = str(exc)
            data["output"] = output

    return data
