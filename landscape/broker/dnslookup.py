import logging

from twisted.names import dns
from twisted.names.client import Resolver


def discover_server():
    resolver = Resolver()
    resolver.parseConfig("/etc/resolv.conf")
    d = _lookup_server_record(resolver)
    d.addErrback(_lookup_hostname, resolver)
    return d


def lookup_server_record(resolver):
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
    hostname = "landscape.localdomain"

    def lookup_done(result):
        return result

    def lookup_failed(result):
        logging.info("Name lookup of %s failed." % hostname)
        return None

    d = resolver.getHostByName(hostname)
    d.addCallback(lookup_done)
    d.addErrback(lookup_failed)
    return d
