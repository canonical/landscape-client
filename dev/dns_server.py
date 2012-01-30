#!/usr/bin/env python
import argparse
import sys
from twisted.internet import reactor, defer
from twisted.names import dns, common
from twisted.names.server import DNSServerFactory


PORT = 5553
SRV_RESPONSE = 'lds1.mylandscapehost.com'
A_RESPONSE = '127.0.0.1'


class SimpleResolver(common.ResolverBase):
    def _lookup(self, name, cls, typ, timeout):
        """
        Respond to DNS requests.  See documentation for
        L{twisted.names.common.ResolverBase}.
        """
        # This nameserver returns the same result all the time, regardless
        # of what name the client asks for.
        results = []
        ttl = 60
        if typ == dns.SRV:
            record = dns.Record_SRV(0, 1, 80, SRV_RESPONSE, ttl)
            owner = '_landscape._tcp.mylandscapehost.com'
            results.append(dns.RRHeader(owner, record.TYPE, dns.IN, ttl,
                                        record, auth=True))
        elif typ == dns.A:
            record = dns.Record_A(A_RESPONSE)
            owner = 'landscape.localdomain'
            results.append(dns.RRHeader(owner, record.TYPE, dns.IN, ttl,
                                        record, auth=True))

        authority = []
        return defer.succeed((results, authority, []))


def parse_command_line(args):
    global SRV_RESPONSE, A_RESPONSE, PORT
    description = """
    This test tool responds to DNS queries for SRV and A records.  It always
    responds with the same result regardless of the query string sent by the
    client.

    To test this tool, try the following commands:
    dig -p 5553 @127.0.0.1 SRV _landscape._tcp.mylandscapehost.com

    dig -p 5553 @127.0.0.1 localhost.localdomain
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--srv-response", type=str,
                        help="Give this reply to SRV queries (eg: localhost)")
    parser.add_argument("--a-response", type=str,
                        help="Give this reply to A queries (eg: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5553,
                        help="Listen on this port (default 5553).  DNS "
                        "normally runs on port 53")

    args = vars(parser.parse_args())
    SRV_RESPONSE = args["srv_response"]
    A_RESPONSE = args["a_response"]
    PORT = args["port"]


def main():
    parse_command_line(sys.argv)

    simple_resolver = SimpleResolver()
    factory = DNSServerFactory(authorities=[simple_resolver], verbose=1)
    protocol = dns.DNSDatagramProtocol(factory)
    print "starting reactor on port %s.." % PORT
    reactor.listenTCP(PORT, factory)
    reactor.listenUDP(PORT, protocol)
    reactor.run()
    print "reactor stopped..."


if __name__ == "__main__":
    main()
