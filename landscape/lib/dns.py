"""DNS lookups for server autodiscovery."""

import logging
from twisted.names import dns
from twisted.names.client import Resolver


def discover_server(autodiscover_srv_query_string="",
                    autodiscover_a_query_string="", resolver=None):
    """
    Look up the dns location of the landscape server.

    @param autodiscover_srv_query_string: The query string to send to the DNS
        server when making a SRV query.
    @param autodiscover_a_query_string: The query string to send to the DNS
        server when making a A query.
    @type resolver: The resolver to use.  If none is specified a resolver that
        uses settings from /etc/resolv.conf will be created. (Testing only)
    """
    if not resolver:
        resolver = Resolver("/etc/resolv.conf")
    d = _lookup_server_record(resolver, autodiscover_srv_query_string)
    d.addErrback(_lookup_hostname, resolver, autodiscover_a_query_string)
    return d


def _lookup_server_record(resolver, service_name):
    """
    Do a DNS SRV record lookup for the location of the landscape server.

    @type resolver: A resolver to use for DNS lookups
        L{twisted.names.client.Resolver}.
    @param service_name: The query string to send to the DNS server when
        making a SRV query.
    @return: A deferred containing either the hostname of the landscape server
        if found or an empty string if not found.
    """
    def lookup_done(result):
        name = ""
        for item in result:
            for row in item:
                if row.type == dns.SRV:
                    name = row.payload.target.name
                    break
        return name

    def lookup_failed(result):
        logging.info("SRV lookup of %s failed." % service_name)
        return result

    d = resolver.lookupService(service_name)
    d.addCallback(lookup_done)
    d.addErrback(lookup_failed)
    return d


def _lookup_hostname(result, resolver, hostname):
    """
    Do a DNS name lookup for the location of the landscape server.

    @param result: The result from a call to lookup_server_record.
    @param resolver: The resolver to use for DNS lookups.
    @param hostname: The query string to send to the DNS server when making
        a A query.
    @param return: A deferred containing the ip address of the landscape
        server if found or None if not found.
    """
    def lookup_done(result):
        return result

    def lookup_failed(result):
        logging.info("Name lookup of %s failed." % hostname)
        return result

    d = resolver.getHostByName(hostname)
    d.addCallback(lookup_done)
    d.addErrback(lookup_failed)
    return d
