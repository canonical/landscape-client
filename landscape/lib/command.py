import commands

class CommandError(Exception):

    def __init__(self, exit_status):
        self.exit_status = exit_status

    def __str__(self):
        return "Command exited with status %d" % self.exit_status

    def __repr__(self):
        return "<CommandError exit_status=%d>" % self.exit_status

def run_command(command):
    """
    Execute a command in a shell and return the command's output. If the
    command's exit status is not 0 a CommandError exception is raised.
    """
    exit_status, output = commands.getstatusoutput(command)
    # shift down 8 bits to get shell-like exit codes
    exit_status = exit_status >> 8
    if exit_status != 0:
        raise CommandError(exit_status)
    return output
