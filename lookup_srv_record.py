from twisted.internet import reactor
import twisted.names.client
from twisted.names import dns


def do_lookup():
    d = twisted.names.client.lookupService('_landscape._tcp.mylandscapehost.com')
    d.addBoth(lookup_done)


def lookup_done(result):
    try:
        for item in result:
            for row in item:
                if row.type == dns.SRV:
                    print row.payload.target
                    break
                elif row.type == dns.A:
                    pass
                else:
                    pass
    finally:
        reactor.stop()

reactor.callLater(0, do_lookup)
reactor.run()
