from optparse import OptionParser
from StringIO import StringIO
import sys

import pycurl

from twisted.internet.threads import deferToThread


def fetch(url, post=False, data="", headers={}, cainfo=None, curl=None):
    """Retrieve a URL and return the content.

    @param url: The url to be fetched.
    @param post: If true, the POST method will be used (defaults to GET).
    @param data: Data to be sent to the server as the POST content.
    @param headers: Dictionary of header => value entries to be used
                    on the request.
    @param cainfo: Path to the file with CA certificates.
    """
    output = StringIO(data)
    input = StringIO()

    if curl is None:
        curl = pycurl.Curl()

    if post:
        curl.setopt(pycurl.POST, True)

        if data:
            curl.setopt(pycurl.POSTFIELDSIZE, len(data))
            curl.setopt(pycurl.READFUNCTION, output.read)

    if cainfo and url.startswith("https:"):
        curl.setopt(pycurl.CAINFO, cainfo)

    if headers:
        curl.setopt(pycurl.HTTPHEADER,
                    ["%s: %s" % pair for pair in sorted(headers.iteritems())])

    curl.setopt(pycurl.URL, url)
    curl.setopt(pycurl.FOLLOWLOCATION, True)
    curl.setopt(pycurl.MAXREDIRS, 5)
    curl.setopt(pycurl.WRITEFUNCTION, input.write)
    curl.perform()

    return input.getvalue()


def test(args):
    parser = OptionParser()
    parser.add_option("--method", default="GET")
    parser.add_option("--data", default="")
    parser.add_option("--cainfo")
    options, (url,) = parser.parse_args(args)
    print fetch(url, options.method, data=options.data, cainfo=options.cainfo)


def fetch_async(*args, **kwargs):
    return deferToThread(fetch, *args, **kwargs)


if __name__ == "__main__":
    test(sys.argv[1:])
