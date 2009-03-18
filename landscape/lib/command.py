import commands

class CommandError(Exception):

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
    Execute a command in a shell and return the command's output. If the
    command's exit status is not 0 a CommandError exception is raised.
    """
    exit_status, output = commands.getstatusoutput(command)
    # shift down 8 bits to get shell-like exit codes
    exit_status = exit_status >> 8
    if exit_status != 0:
        raise CommandError(command, exit_status, output)
    return output
