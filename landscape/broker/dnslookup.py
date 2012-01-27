import logging

from twisted.names import dns
from twisted.names.client import Resolver


def discover_server():
    """
    Look up the dns location of the landscape server.
    """
    resolver = Resolver()
    resolver.parseConfig("/etc/resolv.conf")
    d = _lookup_server_record(resolver)
    d.addErrback(_lookup_hostname, resolver)
    return d


def lookup_server_record(resolver):
    """
    Do a DNS SRV record lookup for the location of the landscape server.

    @type resolver: A resolver to use for DNS lookups
        L{twisted.names.client.Resolver}.
    @return: A deferred containing either the hostname of the landscape server
        if found or an empty string if not found.
    """
    service_name = "_landscape._tcp.mylandscapehost.com"

    def lookup_done(result):
        name = ""
        for item in result:
            for row in item:
                if row.type == dns.SRV:
                    name = row.payload.target
                    break
        return name

    def lookup_failed(result):
        logging.info("SRV lookup of %s failed." % service_name)
        return result

    d = resolver.lookupService(service_name)
    d.addCallback(lookup_done)
    d.addErrback(lookup_failed)
    return d


def lookup_hostname(result, resolver):
    """
    Do a DNS name lookup for the location of the landscape server.

    @param result: The result from a call to lookup_server_record.
    @param resolver: The resolver to use for DNS lookups.
    @param return: A deferred containing the ip address of the landscape
        server if found or None if not found.
    """
    hostname = "landscape.localdomain"

    def lookup_done(result):
        return result

    def lookup_failed(result):
        logging.info("Name lookup of %s failed." % hostname)
        return result

    d = resolver.getHostByName(hostname)
    d.addCallback(lookup_done)
    d.addErrback(lookup_failed)
    return d
