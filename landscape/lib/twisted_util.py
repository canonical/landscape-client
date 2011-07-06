from twisted.internet.defer import DeferredList, Deferred
from twisted.internet.protocol import ProcessProtocol
from twisted.internet.process import Process, ProcessReader
from twisted.internet import reactor

import cStringIO


def gather_results(deferreds, consume_errors=False):
    d = DeferredList(deferreds, fireOnOneErrback=1,
                     consumeErrors=consume_errors)
    d.addCallback(lambda r: [x[1] for x in r])
    d.addErrback(lambda f: f.value.subFailure)
    return d


class AllOutputProcessProtocol(ProcessProtocol):
    """A process protocol for getting stdout, stderr and exit code."""

    def __init__(self, deferred):
        self.deferred = deferred
        self.outBuf = cStringIO.StringIO()
        self.errBuf = cStringIO.StringIO()
        self.outReceived = self.outBuf.write
        self.errReceived = self.errBuf.write

    def processEnded(self, reason):
        out = self.outBuf.getvalue()
        err = self.errBuf.getvalue()
        e = reason.value
        code = e.exitCode
        if e.signal:
            self.deferred.errback((out, err, e.signal))
        else:
            self.deferred.callback((out, err, code))


def spawn_process(executable, args=(), env={}, path=None, uid=None, gid=None,
                  wait_pipes=True):
    """
    Spawn a process using Twisted reactor.

    Return a deferred which will be called with process stdout, stderr and exit
    code.

    NOTE: compared to reactor.spawnProcess, this version does NOT require the
    executable name as first element of args.
    """

    list_args = [executable]
    list_args.extend(args)

    result = Deferred()
    protocol = AllOutputProcessProtocol(result)
    process = reactor.spawnProcess(protocol, executable, args=list_args, env=env,
                                   path=path, uid=uid, gid=gid)

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
                for pipe in process.pipes.itervalues():
                    if isinstance(pipe, ProcessReader):
                        # Read whatever is left
                        pipe.doRead()
                    pipe.stopReading()
                process.pipes = {}
            Process.maybeCallProcessEnded(process)

        process.maybeCallProcessEnded = maybeCallProcessEnded

    return result
