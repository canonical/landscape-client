"""Shell commands execution."""
import commands

class CommandError(Exception):
    """
    Raised by L{run_command} in case of non-0 exit code.

    @cvar command: The shell command that failed.
    @cvar exit_status: Its non-zero exit status.
    @cvar output: The command's output.
    """
    def __init__(self, command, exit_status, output):
        self.command = command
        self.exit_status = exit_status
        self.output = output

    def __str__(self):
        return "'%s' exited with status %d (%s)" % (
            self.command, self.exit_status, self.output)

    def __repr__(self):
        return "<CommandError command=<%s> exit_status=%d output=<%s>>" % (
            self.command, self.exit_status, self.output)


def run_command(command):
    """
    Execute a command in a shell and return the command's output.

    If the command's exit status is not 0 a L{CommandError} exception
    is raised.
    """
    exit_status, output = commands.getstatusoutput(command)
    # shift down 8 bits to get shell-like exit codes
    exit_status = exit_status >> 8
    if exit_status != 0:
        raise CommandError(command, exit_status, output)
    return output
