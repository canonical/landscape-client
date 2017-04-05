import io

from twisted.internet.defer import DeferredList, Deferred
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.process import Process, ProcessReader
from twisted.internet import reactor
from twisted.python.failure import Failure
from twisted.python.compat import itervalues, networkString

from landscape.lib.encoding import encode_values


class SignalError(Exception):
    """An error if the process was terminated by a signal."""


def gather_results(deferreds, consume_errors=False):
    d = DeferredList(deferreds, fireOnOneErrback=1,
                     consumeErrors=consume_errors)
    d.addCallback(lambda r: [x[1] for x in r])
    d.addErrback(lambda f: f.value.subFailure)
    return d


class AllOutputProcessProtocol(ProcessProtocol):
    """A process protocol for getting stdout, stderr and exit code."""

    def __init__(self, deferred, stdin=None, line_received=None):
        self.deferred = deferred
        self.outBuf = io.BytesIO()
        self.errBuf = io.BytesIO()
        self.errReceived = self.errBuf.write
        self.stdin = stdin
        self.line_received = line_received
        self._partial_line = b""

    def connectionMade(self):
        if self.stdin is not None:
            self.transport.write(networkString(self.stdin))
            self.transport.closeStdin()

    def outReceived(self, data):
        self.outBuf.write(data)

        if self.line_received is None:
            return

        # data may contain more than one line, so we split the output and save
        # the last line. If it's an empty string nothing happens, otherwise it
        # will be returned once complete
        lines = data.split(b"\n")
        lines[0] = self._partial_line + lines[0]
        self._partial_line = lines.pop()

        for line in lines:
            self.line_received(line)

    def processEnded(self, reason):
        if self._partial_line:
            self.line_received(self._partial_line)
            self._partial_line = b""
        out = self.outBuf.getvalue()
        err = self.errBuf.getvalue()
        e = reason.value
        code = e.exitCode
        if e.signal:
            failure = Failure(SignalError(out, err, e.signal))
            self.deferred.errback(failure)
        else:
            self.deferred.callback((out, err, code))


def spawn_process(executable, args=(), env={}, path=None, uid=None, gid=None,
                  usePTY=False, wait_pipes=True, line_received=None,
                  stdin=None):
    """
    Spawn a process using Twisted reactor.

    Return a deferred which will be called with process stdout, stderr and exit
    code.

    @param wait_pipes: if set to False, don't wait for stdin/stdout pipes to
        close when process ends.
    @param line_received: an optional callback called with every line of
        output from the process as parameter.

    @note: compared to reactor.spawnProcess, this version does NOT require the
    executable name as first element of args.
    """

    list_args = [executable]
    list_args.extend(args)

    result = Deferred()
    protocol = AllOutputProcessProtocol(result, stdin=stdin,
                                        line_received=line_received)
    env = encode_values(env)
    process = reactor.spawnProcess(protocol, executable, args=list_args,
                                   env=env, path=path, uid=uid, gid=gid,
                                   usePTY=usePTY)

    if not wait_pipes:

        def maybeCallProcessEnded():
            """A less strict version of Process.maybeCallProcessEnded.

            This behaves exactly like the original method, but in case the
            process has ended already and sent us a SIGCHLD, it doesn't wait
            for the stdin/stdout pipes to close, because the child process
            itself might have passed them to its own child processes.

            @note: Twisted 8.2 now has a processExited hook that could
                be used in place of this workaround.
            """
            if process.pipes and not process.pid:
                for pipe in itervalues(process.pipes):
                    if isinstance(pipe, ProcessReader):
                        # Read whatever is left
                        pipe.doRead()
                    pipe.stopReading()
                process.pipes = {}
            Process.maybeCallProcessEnded(process)

        process.maybeCallProcessEnded = maybeCallProcessEnded

    return result
