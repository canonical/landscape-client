from twisted.internet.defer import DeferredList


def gather_results(deferreds, consume_errors=False):
    d = DeferredList(deferreds, fireOnOneErrback=1,
                     consumeErrors=consume_errors)
    d.addCallback(lambda r: [x[1] for x in r])
    d.addErrback(lambda f: f.value.subFailure)
    return d
