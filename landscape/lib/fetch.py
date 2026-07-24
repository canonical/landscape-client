import gzip
import io
import os
import ssl
import sys
import urllib.error
import urllib.request
import zlib
from argparse import ArgumentParser
from logging import warning

from twisted.internet.defer import DeferredList
from twisted.internet.threads import deferToThread


class FetchError(Exception):
    pass


class HTTPCodeError(FetchError):
    def __init__(self, http_code, body):
        self.http_code = http_code
        self.body = body

    def __str__(self):
        return f"Server returned HTTP code {self.http_code:d}"

    def __repr__(self):
        return f"<HTTPCodeError http_code={self.http_code:d}>"


class TransportError(FetchError):
    def __init__(self, error_code, message):
        self.error_code = error_code
        self._message = message

    def __str__(self):
        return f"Error {self.error_code:d}: {self.message}"

    def __repr__(self):
        return f"<TransportError args=({self.error_code:d}, '{self.message}')>"

    @property
    def message(self):
        return self._message


# Backwards-compatible alias for external importers of landscape-lib that
# referenced the old name. Deprecated: use TransportError instead.
PyCurlError = TransportError


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A redirect handler that stops urllib from following HTTP redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _maybe_decompress(body, content_encoding):
    """Decompress C{body} according to the given C{Content-Encoding} value."""
    content_encoding = (content_encoding or "").lower()
    if "gzip" in content_encoding:
        return gzip.decompress(body)
    if "deflate" in content_encoding:
        return zlib.decompress(body)
    return body


def _fetch_urllib(
    url,
    post=False,
    data="",
    headers={},
    cainfo=None,
    connect_timeout=30,
    insecure=False,
    follow=True,
    user_agent=None,
    proxy=None,
):
    """Retrieve a URL using the stdlib urllib backend.

    See L{fetch} for the meaning of the parameters. Failures are translated
    into the same L{HTTPCodeError} and L{TransportError} exceptions raised by
    the pycurl backend so that callers can handle both backends uniformly.
    """
    if isinstance(url, bytes):
        url = url.decode("ascii")

    if not isinstance(data, bytes):
        data = data.encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data if post else None,
        method="POST" if post else "GET",
    )

    req.add_header("Accept-Encoding", "gzip, deflate")

    if headers:
        for key, value in headers.items():
            req.add_header(key, value)

    if user_agent is not None:
        if isinstance(user_agent, bytes):
            user_agent = user_agent.decode("ascii")
        req.add_header("User-Agent", user_agent)

    ctx = None
    if url.startswith("https:"):
        ctx = ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif cainfo:
            if not os.access(cainfo, os.R_OK):
                warning(
                    "SSL certificate provided is not accessible by landscape "
                    + "client. Please place in directory that is readable such "
                    + "as '/etc/ssl/certs'",
                )
            else:
                ctx.load_verify_locations(cafile=cainfo)

    handlers = []
    if proxy is not None:
        if isinstance(proxy, bytes):
            proxy = proxy.decode("ascii")
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
        )

    if not follow:
        handlers.append(_NoRedirectHandler())

    if ctx is not None:
        handlers.append(urllib.request.HTTPSHandler(context=ctx))

    opener = urllib.request.build_opener(*handlers)

    try:
        response = opener.open(req, timeout=connect_timeout)
        body = response.read()
        http_code = response.getcode()
    except urllib.error.HTTPError as e:
        body = _maybe_decompress(e.read(), e.headers.get("Content-Encoding"))
        raise HTTPCodeError(e.code, body)
    except urllib.error.URLError as e:
        # Map urllib/ssl failures onto the libcurl error codes that callers
        # (e.g. registration.register) already branch on, so error handling
        # is uniform across the pycurl and urllib backends.
        reason = e.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise TransportError(60, str(reason)) from e  # CURLE_SSL_CACERT
        elif isinstance(reason, ssl.SSLError):
            raise TransportError(35, str(reason)) from e  # CURLE_SSL_CONNECT_ERROR
        else:
            raise TransportError(7, str(e)) from e  # CURLE_COULDNT_CONNECT
    except Exception as e:
        raise TransportError(0, str(e)) from e  # unknown/unclassified error

    body = _maybe_decompress(body, response.headers.get("Content-Encoding"))

    if http_code != 200:
        raise HTTPCodeError(http_code, body)

    return body


def fetch(
    url,
    post=False,
    data="",
    headers={},
    cainfo=None,
    curl=None,
    connect_timeout=30,
    total_timeout=600,
    insecure=False,
    follow=True,
    user_agent=None,
    proxy=None,
    http_client="pycurl",
):
    """Retrieve a URL and return the content.

    @param url: The url to be fetched.
    @param post: If true, the POST method will be used (defaults to GET).
    @param data: Data to be sent to the server as the POST content.
    @param headers: Dictionary of header => value entries to be used on the
        request.
    @param curl: A pycurl.Curl instance to use. If not provided, one will be
        created.
    @param cainfo: Path to the file with CA certificates.
    @param insecure: If true, perform curl using insecure option which will
        not attempt to verify authenticity of the peer's certificate. (Used
        during autodiscovery)
    @param follow: If True, follow HTTP redirects (default True).
    @param user_agent: The user-agent to set in the request.
    @param proxy: The proxy url to use for the request.
    @param http_client: The HTTP backend to use ('pycurl' or 'urllib').
    """
    if http_client == "urllib":
        return _fetch_urllib(
            url,
            post=post,
            data=data,
            headers=headers,
            cainfo=cainfo,
            connect_timeout=connect_timeout,
            insecure=insecure,
            follow=follow,
            user_agent=user_agent,
            proxy=proxy,
        )

    import pycurl

    if not isinstance(data, bytes):
        data = data.encode("utf-8")
    output = io.BytesIO(data)
    input = io.BytesIO()

    if curl is None:
        curl = pycurl.Curl()

    curl.setopt(pycurl.URL, url.encode("ascii"))

    if post:
        curl.setopt(pycurl.POST, True)

        if data:
            curl.setopt(pycurl.POSTFIELDSIZE, len(data))
            curl.setopt(pycurl.READFUNCTION, output.read)

    if cainfo and url.startswith("https:"):
        if not os.access(cainfo, os.R_OK):
            warning(
                "SSL certificate provided is not accessible by landscape "
                + "client. Please place in directory that is readable such "
                + "as '/etc/ssl/certs'",
            )
            # log error here
        curl.setopt(pycurl.CAINFO, cainfo.encode("ascii"))

    if headers:
        curl.setopt(
            pycurl.HTTPHEADER,
            [f"{key}: {value}" for (key, value) in sorted(headers.items())],
        )

    if insecure:
        curl.setopt(pycurl.SSL_VERIFYPEER, False)

    if follow:
        curl.setopt(pycurl.FOLLOWLOCATION, 1)

    if user_agent is not None:
        curl.setopt(pycurl.USERAGENT, user_agent.encode("ascii"))

    if proxy is not None:
        curl.setopt(pycurl.PROXY, proxy.encode("ascii"))

    curl.setopt(pycurl.MAXREDIRS, 5)
    curl.setopt(pycurl.CONNECTTIMEOUT, connect_timeout)
    curl.setopt(pycurl.LOW_SPEED_LIMIT, 1)
    curl.setopt(pycurl.LOW_SPEED_TIME, total_timeout)
    curl.setopt(pycurl.NOSIGNAL, 1)
    curl.setopt(pycurl.WRITEFUNCTION, input.write)
    curl.setopt(pycurl.DNS_CACHE_TIMEOUT, 0)
    curl.setopt(pycurl.ENCODING, b"gzip,deflate")

    try:
        curl.perform()
    except pycurl.error as e:
        raise TransportError(e.args[0], e.args[1]) from e

    body = input.getvalue()

    http_code = curl.getinfo(pycurl.HTTP_CODE)
    if http_code != 200:
        raise HTTPCodeError(http_code, body)

    return body


def fetch_async(*args, **kwargs):
    """Retrieve a URL asynchronously.

    @return: A C{Deferred} resulting in the URL content.
    """
    return deferToThread(fetch, *args, **kwargs)


def fetch_many_async(urls, callback=None, errback=None, **kwargs):
    """
    Retrieve a list of URLs asynchronously.

    @param callback: Optionally, a function that will be fired one time for
        each successful URL, and will be passed its content and the URL itself.
    @param errback: Optionally, a function that will be fired one time for each
        failing URL, and will be passed the failure and the URL itself.
    @return: A C{DeferredList} whose callback chain will be fired as soon as
        all downloads have terminated. If an error occurs, the errback chain
        of the C{DeferredList} will be fired immediatly.
    """
    results = []
    for url in urls:
        result = fetch_async(url, **kwargs)
        if callback:
            result.addCallback(callback, url)
        if errback:
            result.addErrback(errback, url)
        results.append(result)
    return DeferredList(results, fireOnOneErrback=True, consumeErrors=True)


def url_to_filename(url, directory=None):
    """Return the last component of the given C{url}.

    @param url: The URL to get the filename from.
    @param directory: Optionally a path to prepend to the returned filename.

    @note: Any trailing slash in the C{url} will be removed
    """
    filename = url.rstrip("/").split("/")[-1]
    if directory is not None:
        filename = os.path.join(directory, filename)
    return filename


def fetch_to_files(urls, directory, logger=None, **kwargs):
    """
    Retrieve a list of URLs and save their content as files in a directory.

    @param urls: The list URLs to fetch.
    @param directory: The directory to save the files to, the name of the file
        will equal the last fragment of the URL.
    @param logger: Optional function to be used to log errors for failed URLs.
    """

    def write(data, url):
        filename = url_to_filename(url, directory=directory)
        fd = open(filename, "wb")
        fd.write(data)
        fd.close()

    def log_error(failure, url):
        if logger:
            logger(
                f"Couldn't fetch file from {url} ({str(failure.value)})",
            )
        return failure

    return fetch_many_async(urls, callback=write, errback=log_error, **kwargs)


def test(args):
    parser = ArgumentParser()
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--data", default="")
    parser.add_argument("--cainfo")
    options = parser.parse_args(args)
    url = options.positional
    print(
        fetch(
            url,
            post=options.post,
            data=options.data,
            cainfo=options.cainfo,
        ),
    )


if __name__ == "__main__":
    test(sys.argv[1:])
