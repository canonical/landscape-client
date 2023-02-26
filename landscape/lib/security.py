import subprocess

__all__ = ["get_listeningports"]


class ListeningPort:
    """
    Details about a listeining port in the system
    """

    lsof_cmd = "/usr/bin/lsof"
    awk_cmd = "/usr/bin/awk"

    def __init__(self, cmd, pid, user, kind, mode, port, *args):
        self.cmd = cmd
        self.pid = pid
        self.user = user
        self.kind = kind
        self.mode = mode
        self.port = port

    @property
    def canonical(self):
        return {
            "cmd": self.cmd,
            "pid": self.pid,
            "user": self.user,
            "kind": self.kind,
            "mode": self.mode,
            "port": self.port,
        }

    def __eq__(self, other):
        return (
            self.cmd == other.cmd
            and self.pid == other.pid
            and self.user == other.user
            and self.kind == other.kind
            and self.mode == other.mode
            and self.port == other.port
        )

    def __repr__(self):
        return (
            f"{self.cmd} {self.pid} {self.user} "
            f"{self.kind} {self.mode} {self.port}"
        )


def get_listeningports():

    # Launch lsof to find all ports being used
    ps = subprocess.run(
        [ListeningPort.lsof_cmd, "-i", "-P", "-n"],
        check=True,
        capture_output=True,
    )

    # Filter result with AWK for port listening and
    # select columns: COMMAND, PID, USER, TYPE, MODE, NAME
    ps2 = subprocess.run(
        [
            ListeningPort.awk_cmd,
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
        ports.append(ListeningPort(*elements))

    return ports
