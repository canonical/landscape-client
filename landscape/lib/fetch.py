from optparse import OptionParser
from StringIO import StringIO
import sys

import pycurl

from twisted.internet.threads import deferToThread


class FetchError(Exception):
    pass


class HTTPCodeError(FetchError):

    def __init__(self, http_code, body):
        self.http_code = http_code
        self.body = body

    def __str__(self):
        return "Server returned HTTP code %d" % self.http_code

    def __repr__(self):
        return "<HTTPCodeError http_code=%d>" % self.http_code


class PyCurlError(FetchError):

    def __init__(self, error_code, message):
        self.error_code = error_code
        self._message = message

    def __str__(self):
        return "Error %d: %s" % (self.error_code, self.message)

    def __repr__(self):
        return "<PyCurlError args=(%d, '%s')>" % (self.error_code,
                                                  self.message)

    @property
    def message(self):
        return self._message


def fetch(url, post=False, data="", headers={}, cainfo=None, curl=None,
          connect_timeout=30, total_timeout=600):
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
    curl.setopt(pycurl.CONNECTTIMEOUT, connect_timeout)
    curl.setopt(pycurl.LOW_SPEED_LIMIT, 1)
    curl.setopt(pycurl.LOW_SPEED_TIME, total_timeout)
    curl.setopt(pycurl.NOSIGNAL, 1)
    curl.setopt(pycurl.WRITEFUNCTION, input.write)

    try:
        curl.perform()
    except pycurl.error, e:
        raise PyCurlError(e.args[0], e.args[1])

    body = input.getvalue()

    http_code = curl.getinfo(pycurl.HTTP_CODE)
    if http_code != 200:
        raise HTTPCodeError(http_code, body)

    return body


def test(args):
    parser = OptionParser()
    parser.add_option("--post", action="store_true")
    parser.add_option("--data", default="")
    parser.add_option("--cainfo")
    options, (url,) = parser.parse_args(args)
    print fetch(url, post=options.post, data=options.data,
                cainfo=options.cainfo)


def fetch_async(*args, **kwargs):
    return deferToThread(fetch, *args, **kwargs)


if __name__ == "__main__":
    test(sys.argv[1:])
