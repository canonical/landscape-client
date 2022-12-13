import subprocess

from landscape.client.monitor.plugin import DataWatcher


class LivePatch(DataWatcher):
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
        livepatch_status = get_livepatch_status()
        return livepatch_status


def get_livepatch_status():
    """
    Livepatch returns output formatted like YAML
    """
    try:
        completed_process = subprocess.run(
            ["canonical-livepatch", "status"],
            encoding="utf8", stdout=subprocess.PIPE)
    except FileNotFoundError as exc:
        data = {"code": -1, "exception": str(exc), "output": ""}
    except Exception as exc:
        data = {"code": -2, "exception": str(exc), "output": ""}
    else:
        data = {"code": completed_process.returncode, "exception": "",
                "output": completed_process.stdout}
    return data
