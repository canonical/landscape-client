import os
import re
import logging
from dateutil import parser, tz
from datetime import datetime
import subprocess
from pydantic import BaseModel, validator

__all__ = ["get_listeningports"]

lsof_cmd = "/usr/bin/lsof"
awk_cmd = "/usr/bin/awk"
rkhunter_cmd = "/usr/bin/rkhunter"


class ListeningPort(BaseModel):
    cmd: str
    pid: int
    user: str
    kind: str
    mode: str
    port: int


def get_listeningports():

    # Launch lsof to find all ports being used
    ps = subprocess.run(
        [lsof_cmd, "-i", "-P", "-n"],
        check=True,
        capture_output=True,
    )

    # Filter result with AWK for port listening and
    # select columns: COMMAND, PID, USER, TYPE, MODE, NAME
    ps2 = subprocess.run(
        [
            awk_cmd,
            '$10 ~ "LISTEN" {n=split($9, a, ":"); '
            'print $1" "$2" "$3" "$5" "$8" "a[n]}',
        ],
        input=ps.stdout,
        capture_output=True,
    )

    # Get output
    output = ps2.stdout.decode("utf-8").strip()

    # Build ports information
    ports = []
    for line in output.splitlines():
        elements = line.split(" ")
        ports.append(
            ListeningPort(
                **dict(
                    zip(
                        ["cmd", "pid", "user", "kind", "mode", "port"],
                        elements,
                    )
                )
            )
        )

    return ports


class RKHunterInfo(BaseModel):
    timestamp: str
    files_checked: int
    files_suspect: int
    rootkit_checked: int
    rootkit_suspect: int
    version: str

    @validator("timestamp", pre=True)
    def timesgtamp_validate(cls, timestamp):  # noqa: N805
        return timestamp.isoformat()


class RKHunterBase:

    tzmapping = {
        "CET": tz.gettz("Europe/Berlin"),
        "CEST": tz.gettz("Europe/Berlin"),
    }

    def get_version(self):
        ps = subprocess.run(
            [rkhunter_cmd, "--version"],
            check=True,
            capture_output=True,
        )
        firstline = ps.stdout.decode("utf-8").split("\n")[0].strip()
        return firstline.split(" ")[-1]

    def _extract(self, regex, line, is_timestamp):
        found = re.search(regex, line)
        if found:
            if is_timestamp:
                ts = " ".join(found.groups()[-1].split(" ")[-5:])
                return parser.parse(ts, tzinfos=self.tzmapping)

            else:
                return int(found.groups()[-1])
        else:
            return None

    def _analize(self, lines, from_log=False):
        info = {
            "files_checked": r"^((\[.*\])|)\ *Files checked: (.*?)$",
            "files_suspect": r"^((\[.*\])|)\ *Suspect files: (.*?)$",
            "rootkit_checked": r"^((\[.*\])|)\ *Rootkits checked\ : (.*?)$",
            "rootkit_suspect": r"^((\[.*\])|)\ *Possible rootkits: (.*?)$",
        }

        # Read timestamp from log
        if from_log:
            info["timestamp"] = r"^\[.*\]\ Info: End date is (.*?)$"

        result = {}
        for line in lines:
            if from_log:
                line = line.split("\n")[0]
            for key, value in info.items():
                if key not in result.keys():
                    found = self._extract(value, line, key == "timestamp")
                    if found is not None:
                        result[key] = found
                        if len(result) == len(info):
                            # We got all of them
                            break
        return result


class RKHunterLogReader(RKHunterBase):
    def __init__(self, filename="/var/log/rkhunter.log"):
        self._filename = filename

    def get_last_log(self):

        # Get version
        version = self.get_version()

        # Get file size
        try:
            size = os.stat(self._filename).st_size
        except FileNotFoundError as e:
            logging.warning(f"RKHunter log not found at {self._filename}: {e}")
            size = None
        except PermissionError as e:
            logging.warning(
                "Couldn't read RKHunter's log. Permission denied while "
                f"accesing to {self._filename}: {e}"
            )
            size = None

        if size is not None:
            with open(self._filename, "r") as file:

                # Read last 1024 bytes or whatever is left in reverse
                file.seek(size - min(size, 1024))
                lines = file.readlines()
                lines.reverse()

                # Analize lines
                result = self._analize(lines, from_log=True)
        else:
            result = []

        # We expect 5 fields found
        if len(result) == 5:
            return RKHunterInfo(version=version, **result)
        else:
            return None


class RKHunterLiveInfo(RKHunterBase):
    WARNING_CHECK_LST = [
        "Checking for hidden files and directories",
        "Checking for prerequisites",
        "Checking if SSH root access is allowed",
    ]

    def execute(self):

        # Get version
        version = self.get_version()

        # Execute rkhunter
        ps = subprocess.run(
            [rkhunter_cmd, "-c", "--sk", "--nocolors", "--noappend-log"],
            check=True,
            capture_output=True,
        )
        lines = ps.stdout.decode("utf-8").strip()

        result = self._analize(lines.split("\n"))

        # We expect 4 fields found
        if len(result) == 4:
            return RKHunterInfo(
                timestamp=datetime.now(), version=version, **result
            )
        else:
            return None
