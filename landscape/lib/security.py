import subprocess
from pydantic import BaseModel, validator

__all__ = ["get_listeningports"]

lsof_cmd = "/usr/bin/lsof"
awk_cmd = "/usr/bin/awk"


class ListeningPort(BaseModel):
    cmd: str
    pid: str
    user: str
    kind: str
    mode: str
    port: str

    @validator("pid")
    def pid_must_be_integer(cls, v):  # noqa: N805
        return str(int(v))

    @validator("port")
    def port_must_be_integer(cls, v):  # noqa:N805
        return str(int(v))


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
