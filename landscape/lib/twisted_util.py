from twisted.internet.defer import DeferredList, Deferred
from twisted.internet.protocol import ProcessProtocol
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


def spawn_process(executable, args=(), env={}, path=None, uid=None, gid=None):
    """
    Spawn a process using Twisted reactor.
    Return a process and a deferred which will be called with process stdout,
    stderr and exit code.
    """
    result = Deferred()
    protocol = AllOutputProcessProtocol(result)
    process = reactor.spawnProcess(protocol, executable, args=args, env=env,
                                   path=path, uid=uid, gid=gid)
    return process, result
