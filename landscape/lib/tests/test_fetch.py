import gzip
import io
import os
import ssl
import unittest
import urllib.error
import urllib.request
import zlib
from threading import local
from unittest import mock

import pycurl
from twisted.internet.defer import FirstError

from landscape.lib import testing
from landscape.lib.fetch import (
    HTTPCodeError,
    TransportError,
    _NoRedirectHandler,
    fetch,
    fetch_async,
    fetch_many_async,
    fetch_to_files,
    url_to_filename,
)


class CurlStub:
    def __init__(self, result=None, infos=None, error=None):
        self.result = result
        self.infos = infos
        if self.infos is None:
            self.infos = {pycurl.HTTP_CODE: 200}
        self.options = {}
        self.performed = False
        self.error = error

    def getinfo(self, what):
        if what in self.infos:
            return self.infos[what]
        raise RuntimeError(f"Stub doesn't know about {what:d} info")

    def setopt(self, option, value):
        if isinstance(value, str):
            raise AssertionError("setopt() doesn't accept unicode values")
        if self.performed:
            raise AssertionError("setopt() can't be called after perform()")
        self.options[option] = value

    def perform(self):
        if self.error:
            raise self.error
        if self.performed:
            raise AssertionError("Can't perform twice")
        self.options[pycurl.WRITEFUNCTION](self.result)
        self.performed = True


class CurlManyStub:
    def __init__(self, url_results):
        self.curls = {}
        for url in url_results:
            result = url_results[url]
            if not isinstance(result, tuple):
                body = result
                http_code = 200
            else:
                body = result[0]
                http_code = result[1]
            self.curls[url] = CurlStub(
                result=body,
                infos={pycurl.HTTP_CODE: http_code},
            )

        # Use thread local storage to keep the current CurlStub since
        # CurlManyStub is passed to multiple threads, but the state needs to be
        # local.
        self._local = local()
        self._local.current = None

    def getinfo(self, what):
        if not self._local.current.performed:
            raise AssertionError("getinfo() can't be called before perform()")
        result = self._local.current.getinfo(what)
        self._local.current = None
        return result

    def setopt(self, option, value):
        if option == pycurl.URL:
            # This seems a bit weird, but the curls have a str as key and we
            # want to keep it like this. But when we set the value for pycurl
            # option we already have the encoded bytes object, that's why we
            # have to decode again.
            self._local.current = self.curls[value.decode("ascii")]
        self._local.current.setopt(option, value)

    def perform(self):
        self._local.current.perform()


class Any:
    def __eq__(self, other):
        return True


class FetchTest(
    testing.FSTestCase,
    testing.TwistedTestCase,
    unittest.TestCase,
):
    def test_basic(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", curl=curl)
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_post(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", post=True, curl=curl)
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.POST: True,
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_post_data(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", post=True, data="data", curl=curl)
        self.assertEqual(result, b"result")
        self.assertEqual(curl.options[pycurl.READFUNCTION](), b"data")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.POST: True,
                pycurl.POSTFIELDSIZE: 4,
                pycurl.READFUNCTION: Any(),
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_cainfo(self):
        curl = CurlStub(b"result")
        result = fetch("https://example.com", cainfo="cainfo", curl=curl)
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"https://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.CAINFO: b"cainfo",
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_cainfo_on_http(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", cainfo="cainfo", curl=curl)
        self.assertEqual(result, b"result")
        self.assertTrue(pycurl.CAINFO not in curl.options)

    @mock.patch("landscape.lib.fetch.warning")
    def test_cainfo_inaccessible_cert(self, logging):
        curl = CurlStub(b"result")
        result = fetch("https://example.com", cainfo="cainfo", curl=curl)
        self.assertEqual(result, b"result")
        logging.assert_called_once_with(
            "SSL certificate provided is not accessible by landscape "
            + "client. Please place in directory that is readable such "
            + "as '/etc/ssl/certs'",
        )

    def test_headers(self):
        curl = CurlStub(b"result")
        result = fetch(
            "http://example.com",
            headers={"a": "1", "b": "2"},
            curl=curl,
        )
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.HTTPHEADER: ["a: 1", "b: 2"],
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_timeouts(self):
        curl = CurlStub(b"result")
        result = fetch(
            "http://example.com",
            connect_timeout=5,
            total_timeout=30,
            curl=curl,
        )
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 5,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 30,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_unicode(self):
        """
        The L{fetch} function converts the C{url} parameter to C{bytes} before
        passing it to curl.
        """
        curl = CurlStub(b"result")
        result = fetch("http://example.com", curl=curl)
        self.assertEqual(result, b"result")
        self.assertEqual(curl.options[pycurl.URL], b"http://example.com")
        self.assertTrue(isinstance(curl.options[pycurl.URL], bytes))

    def test_non_200_result(self):
        curl = CurlStub(b"result", {pycurl.HTTP_CODE: 404})
        try:
            fetch("http://example.com", curl=curl)
        except HTTPCodeError as error:
            self.assertEqual(error.http_code, 404)
            self.assertEqual(error.body, b"result")
        else:
            self.fail("HTTPCodeError not raised")

    def test_http_error_str(self):
        self.assertEqual(
            str(HTTPCodeError(501, "")),
            "Server returned HTTP code 501",
        )

    def test_http_error_repr(self):
        self.assertEqual(
            repr(HTTPCodeError(501, "")),
            "<HTTPCodeError http_code=501>",
        )

    def test_pycurl_error(self):
        curl = CurlStub(error=pycurl.error(60, "pycurl error"))
        with self.assertRaises(TransportError) as cm:
            fetch("http://example.com", curl=curl)
        self.assertEqual(cm.exception.error_code, 60)
        self.assertEqual(cm.exception.message, "pycurl error")

    def test_pycurl_insecure(self):
        curl = CurlStub(b"result")
        result = fetch(
            "http://example.com/get-ca-cert",
            curl=curl,
            insecure=True,
        )
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com/get-ca-cert",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.SSL_VERIFYPEER: False,
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_pycurl_error_str(self):
        self.assertEqual(
            str(TransportError(60, "pycurl error")),
            "Error 60: pycurl error",
        )

    def test_pycurl_error_repr(self):
        self.assertEqual(
            repr(TransportError(60, "pycurl error")),
            "<TransportError args=(60, 'pycurl error')>",
        )

    def test_pycurl_follow_true(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", curl=curl, follow=True)
        self.assertEqual(result, b"result")
        self.assertEqual(1, curl.options[pycurl.FOLLOWLOCATION])

    def test_pycurl_follow_false(self):
        curl = CurlStub(b"result")
        result = fetch("http://example.com", curl=curl, follow=False)
        self.assertEqual(result, b"result")
        self.assertNotIn(pycurl.FOLLOWLOCATION, curl.options.keys())

    def test_pycurl_user_agent(self):
        """If provided, the user-agent is set in the request."""
        curl = CurlStub(b"result")
        result = fetch(
            "http://example.com",
            curl=curl,
            user_agent="user-agent",
        )
        self.assertEqual(result, b"result")
        self.assertEqual(b"user-agent", curl.options[pycurl.USERAGENT])

    def test_pycurl_proxy(self):
        """If provided, the proxy is set in the request."""
        curl = CurlStub(b"result")
        proxy = "http://my.little.proxy"
        result = fetch("http://example.com", curl=curl, proxy=proxy)
        self.assertEqual(b"result", result)
        self.assertEqual(proxy.encode("ascii"), curl.options[pycurl.PROXY])

    def test_create_curl(self):
        curls = []

        def pycurl_curl():
            curl = CurlStub(b"result")
            curls.append(curl)
            return curl

        pycurl.Curl = pycurl_curl
        result = fetch("http://example.com")
        curl = curls[0]
        self.assertEqual(result, b"result")
        self.assertEqual(
            curl.options,
            {
                pycurl.URL: b"http://example.com",
                pycurl.FOLLOWLOCATION: 1,
                pycurl.MAXREDIRS: 5,
                pycurl.CONNECTTIMEOUT: 30,
                pycurl.LOW_SPEED_LIMIT: 1,
                pycurl.LOW_SPEED_TIME: 600,
                pycurl.NOSIGNAL: 1,
                pycurl.WRITEFUNCTION: Any(),
                pycurl.DNS_CACHE_TIMEOUT: 0,
                pycurl.ENCODING: b"gzip,deflate",
            },
        )

    def test_async_fetch(self):
        curl = CurlStub(b"result")
        d = fetch_async("http://example.com/", curl=curl)

        def got_result(result):
            self.assertEqual(result, b"result")

        return d.addCallback(got_result)

    def test_async_fetch_with_error(self):
        curl = CurlStub(b"result", {pycurl.HTTP_CODE: 501})
        d = fetch_async("http://example.com/", curl=curl)

        def got_error(failure):
            self.assertEqual(failure.value.http_code, 501)
            self.assertEqual(failure.value.body, b"result")
            return failure

        d.addErrback(got_error)
        self.assertFailure(d, HTTPCodeError)
        return d

    def test_fetch_many_async(self):
        """
        L{fetch_many_async} retrieves multiple URLs, and returns a
        C{DeferredList} firing its callback when all the URLs have
        successfully completed.
        """
        url_results = {"http://good/": b"good", "http://better/": b"better"}

        def callback(result, url):
            self.assertIn(result, url_results.values())
            self.assertIn(url, url_results)
            url_results.pop(url)

        def errback(failure, url):
            self.fail()

        curl = CurlManyStub(url_results)
        d = fetch_many_async(
            url_results.keys(),
            callback=callback,
            errback=errback,
            curl=curl,
        )

        def completed(result):
            self.assertEqual(url_results, {})

        return d.addCallback(completed)

    def test_fetch_many_async_with_error(self):
        """
        L{fetch_many_async} aborts as soon as one URL fails.
        """
        url_results = {
            "http://right/": b"right",
            "http://wrong/": (b"wrong", 501),
            "http://impossible/": b"impossible",
        }
        failed_urls = []

        def errback(failure, url):
            failed_urls.append(url)
            self.assertEqual(failure.value.body, b"wrong")
            self.assertEqual(failure.value.http_code, 501)
            return failure

        curl = CurlManyStub(url_results)
        urls = ["http://right/", "http://wrong/", "http://impossible/"]
        result = fetch_many_async(
            urls,
            callback=None,
            errback=errback,
            curl=curl,
        )

        def check_failure(failure):
            self.assertTrue(
                isinstance(failure.subFailure.value, HTTPCodeError),
            )
            self.assertEqual(failed_urls, ["http://wrong/"])

        self.assertFailure(result, FirstError)
        return result.addCallback(check_failure)

    def test_url_to_filename(self):
        """
        L{url_to_filename} extracts the filename part of an URL, optionally
        prepending a directory path to it.
        """
        self.assertEqual(url_to_filename("http://some/file"), "file")
        self.assertEqual(url_to_filename("http://some/file/"), "file")
        self.assertEqual(
            url_to_filename("http://some/file", directory="dir"),
            os.path.join("dir", "file"),
        )

    def test_fetch_to_files(self):
        """
        L{fetch_to_files} fetches a list of URLs and save their content
        in the given directory.
        """
        url_results = {
            "http://good/file": b"file",
            "http://even/better-file": b"better-file",
        }
        directory = self.makeDir()
        curl = CurlManyStub(url_results)

        result = fetch_to_files(url_results.keys(), directory, curl=curl)

        def check_files(ignored):
            for url, result in url_results.items():
                filename = url.rstrip("/").split("/")[-1]
                fd = open(os.path.join(directory, filename), "rb")
                self.assertEqual(fd.read(), result)
                fd.close()

        result.addCallback(check_files)
        return result

    def test_fetch_to_files_with_trailing_slash(self):
        """
        L{fetch_to_files} discards trailing slashes from the final component
        of the given URLs when saving them as files.
        """
        directory = self.makeDir()
        curl = CurlStub(b"data")

        result = fetch_to_files(["http:///with/slash/"], directory, curl=curl)

        def check_files(ignored):
            os.path.exists(os.path.join(directory, "slash"))

        result.addCallback(check_files)
        return result

    def test_fetch_to_files_with_errors(self):
        """
        L{fetch_to_files} optionally logs an error message as soon as one URL
        fails, and aborts.
        """
        url_results = {
            "http://im/right": b"right",
            "http://im/wrong": (b"wrong", 404),
            "http://im/not": b"not",
        }
        directory = self.makeDir()
        messages = []

        def logger(message):
            return messages.append(message)

        curl = CurlManyStub(url_results)

        result = fetch_to_files(
            url_results.keys(),
            directory,
            logger=logger,
            curl=curl,
        )

        def check_messages(failure):
            self.assertEqual(len(messages), 1)
            self.assertEqual(
                messages[0],
                "Couldn't fetch file from http://im/wrong "
                "(Server returned HTTP code 404)",
            )
            messages.pop()

        def check_files(ignored):
            self.assertEqual(messages, [])
            self.assertFalse(os.path.exists(os.path.join(directory, "wrong")))

        result.addErrback(check_messages)
        result.addCallback(check_files)
        return result

    def test_fetch_to_files_with_non_existing_directory(self):
        """
        The deferred list returned by L{fetch_to_files} results in a failure
        if the destination directory doesn't exist.
        """
        url_results = {"http://im/right": b"right"}
        directory = "i/dont/exist/"
        curl = CurlManyStub(url_results)

        result = fetch_to_files(url_results.keys(), directory, curl=curl)

        def check_error(failure):
            error = str(failure.value.subFailure.value)
            self.assertEqual(
                error,
                ("[Errno 2] No such file or directory: 'i/dont/exist/right'"),
            )
            self.assertFalse(os.path.exists(os.path.join(directory, "right")))

        result.addErrback(check_error)
        return result

    def _urllib_opener(
        self,
        mock_build_opener,
        body=b"result",
        code=200,
        headers=None,
    ):
        """Configure C{mock_build_opener} with an opener returning a response
        with the given C{body}, HTTP C{code} and C{headers}, and return the
        opener mock for further assertions.
        """
        response = mock.MagicMock()
        response.read.return_value = body
        response.getcode.return_value = code
        response.headers = {} if headers is None else headers

        opener = mock.MagicMock()
        opener.open.return_value = response
        mock_build_opener.return_value = opener
        return opener

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_basic(self, mock_build_opener):
        """The C{urllib} backend performs a GET request and returns the body."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch("http://example.com", http_client="urllib")
        self.assertEqual(result, b"result")

        opener.open.assert_called_once()
        req = opener.open.call_args[0][0]
        self.assertEqual(req.full_url, "http://example.com")
        self.assertEqual(req.get_method(), "GET")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_post(self, mock_build_opener):
        """With C{post=True} the C{urllib} backend issues a POST request."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch("http://example.com", post=True, http_client="urllib")
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.data, b"")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_post_data(self, mock_build_opener):
        """POST C{data} is encoded and sent as the request body."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            post=True,
            data="post-data",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.data, b"post-data")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_headers(self, mock_build_opener):
        """If provided, headers are set on the request."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            headers={"Custom-Header": "value"},
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_header("Custom-header"), "value")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_user_agent(self, mock_build_opener):
        """If provided, the user-agent is set in the request."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            user_agent="my-user-agent",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_header("User-agent"), "my-user-agent")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_proxy(self, mock_build_opener):
        """If provided, the proxy is set for both http and https."""
        self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            proxy="http://127.0.0.1:8080",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        handlers = mock_build_opener.call_args[0]
        proxy_handlers = [
            h for h in handlers if isinstance(h, urllib.request.ProxyHandler)
        ]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(
            proxy_handlers[0].proxies,
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
        )

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_follow_false(self, mock_build_opener):
        """With C{follow=False} a no-redirect handler is installed."""
        self._urllib_opener(mock_build_opener)

        result = fetch("http://example.com", follow=False, http_client="urllib")
        self.assertEqual(result, b"result")

        handlers = mock_build_opener.call_args[0]
        redirect_handlers = [
            h for h in handlers if isinstance(h, urllib.request.HTTPRedirectHandler)
        ]
        self.assertEqual(len(redirect_handlers), 1)

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_non_200(self, mock_build_opener):
        """A non-200 response raises L{HTTPCodeError} with code and body."""
        self._urllib_opener(mock_build_opener, body=b"error body", code=404)

        with self.assertRaises(HTTPCodeError) as cm:
            fetch("http://example.com", http_client="urllib")
        self.assertEqual(cm.exception.http_code, 404)
        self.assertEqual(cm.exception.body, b"error body")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_ssl_verification_error(self, mock_build_opener):
        """An SSL certificate verification failure maps to error code 60."""
        opener = mock.MagicMock()
        reason = ssl.SSLCertVerificationError(1, "self-signed certificate")
        opener.open.side_effect = urllib.error.URLError(reason)
        mock_build_opener.return_value = opener

        with self.assertRaises(TransportError) as cm:
            fetch("https://example.com", http_client="urllib")
        self.assertEqual(cm.exception.error_code, 60)
        self.assertIn("self-signed certificate", cm.exception.message)

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_ssl_error(self, mock_build_opener):
        """A generic SSL error maps to error code 35."""
        opener = mock.MagicMock()
        reason = ssl.SSLError("some ssl error")
        opener.open.side_effect = urllib.error.URLError(reason)
        mock_build_opener.return_value = opener

        with self.assertRaises(TransportError) as cm:
            fetch("https://example.com", http_client="urllib")
        self.assertEqual(cm.exception.error_code, 35)
        self.assertIn("some ssl error", cm.exception.message)

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_other_error(self, mock_build_opener):
        """A non-SSL connection error maps to error code 7."""
        opener = mock.MagicMock()
        opener.open.side_effect = urllib.error.URLError("connection refused")
        mock_build_opener.return_value = opener

        with self.assertRaises(TransportError) as cm:
            fetch("http://example.com", http_client="urllib")
        self.assertEqual(cm.exception.error_code, 7)
        self.assertIn("connection refused", cm.exception.message)

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_gzip(self, mock_build_opener):
        """A gzip-encoded response body is transparently decompressed."""
        self._urllib_opener(
            mock_build_opener,
            body=gzip.compress(b"gzip-decoded"),
            headers={"Content-Encoding": "gzip"},
        )

        result = fetch("http://example.com", http_client="urllib")
        self.assertEqual(result, b"gzip-decoded")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_deflate(self, mock_build_opener):
        """A deflate-encoded response body is transparently decompressed."""
        self._urllib_opener(
            mock_build_opener,
            body=zlib.compress(b"deflate-decoded"),
            headers={"Content-Encoding": "deflate"},
        )

        result = fetch("http://example.com", http_client="urllib")
        self.assertEqual(result, b"deflate-decoded")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_bytes_url(self, mock_build_opener):
        """A C{bytes} URL is decoded before the request is built."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch(b"http://example.com", http_client="urllib")
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.full_url, "http://example.com")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_bytes_user_agent(self, mock_build_opener):
        """A C{bytes} user-agent is decoded before being set as a header."""
        opener = self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            user_agent=b"my-user-agent",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        req = opener.open.call_args[0][0]
        self.assertEqual(req.get_header("User-agent"), "my-user-agent")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_bytes_proxy(self, mock_build_opener):
        """A C{bytes} proxy is decoded before the proxy handler is built."""
        self._urllib_opener(mock_build_opener)

        result = fetch(
            "http://example.com",
            proxy=b"http://127.0.0.1:8080",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")

        handlers = mock_build_opener.call_args[0]
        proxy_handlers = [
            h for h in handlers if isinstance(h, urllib.request.ProxyHandler)
        ]
        self.assertEqual(len(proxy_handlers), 1)
        self.assertEqual(
            proxy_handlers[0].proxies,
            {"http": "http://127.0.0.1:8080", "https": "http://127.0.0.1:8080"},
        )

    @mock.patch("landscape.lib.fetch.ssl.create_default_context")
    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_insecure(self, mock_build_opener, mock_create_ctx):
        """With C{insecure=True} over HTTPS certificate checks are disabled."""
        self._urllib_opener(mock_build_opener)
        ctx = mock_create_ctx.return_value

        result = fetch(
            "https://example.com",
            insecure=True,
            http_client="urllib",
        )
        self.assertEqual(result, b"result")
        self.assertFalse(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_NONE)

    @mock.patch("landscape.lib.fetch.ssl.create_default_context")
    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_cainfo(self, mock_build_opener, mock_create_ctx):
        """Over HTTPS a readable cainfo file is loaded into the SSL context."""
        self._urllib_opener(mock_build_opener)
        ctx = mock_create_ctx.return_value
        cainfo = self.makeFile("cert-data")

        result = fetch(
            "https://example.com",
            cainfo=cainfo,
            http_client="urllib",
        )
        self.assertEqual(result, b"result")
        ctx.load_verify_locations.assert_called_once_with(cafile=cainfo)

    @mock.patch("landscape.lib.fetch.warning")
    @mock.patch("landscape.lib.fetch.ssl.create_default_context")
    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_cainfo_not_accessible(
        self,
        mock_build_opener,
        mock_create_ctx,
        mock_warning,
    ):
        """Over HTTPS an unreadable cainfo path logs a warning and is skipped."""
        self._urllib_opener(mock_build_opener)
        ctx = mock_create_ctx.return_value

        result = fetch(
            "https://example.com",
            cainfo="/nonexistent/path/cert.pem",
            http_client="urllib",
        )
        self.assertEqual(result, b"result")
        mock_warning.assert_called_once()
        ctx.load_verify_locations.assert_not_called()

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_http_error(self, mock_build_opener):
        """An C{HTTPError} from the opener is raised as L{HTTPCodeError}."""
        opener = mock.MagicMock()
        opener.open.side_effect = urllib.error.HTTPError(
            "http://example.com",
            500,
            "Server Error",
            {},
            io.BytesIO(b"error body"),
        )
        mock_build_opener.return_value = opener

        with self.assertRaises(HTTPCodeError) as cm:
            fetch("http://example.com", http_client="urllib")
        self.assertEqual(cm.exception.http_code, 500)
        self.assertEqual(cm.exception.body, b"error body")

    @mock.patch("landscape.lib.fetch.urllib.request.build_opener")
    def test_urllib_unexpected_error(self, mock_build_opener):
        """An unexpected error is wrapped in L{TransportError} with code 0."""
        opener = mock.MagicMock()
        opener.open.side_effect = ValueError("boom")
        mock_build_opener.return_value = opener

        with self.assertRaises(TransportError) as cm:
            fetch("http://example.com", http_client="urllib")
        self.assertEqual(cm.exception.error_code, 0)
        self.assertIn("boom", cm.exception.message)

    def test_no_redirect_handler_returns_none(self):
        """C{_NoRedirectHandler} suppresses redirects by returning C{None}."""
        handler = _NoRedirectHandler()
        result = handler.redirect_request(
            None,
            None,
            302,
            "Found",
            {},
            "http://example.com/other",
        )
        self.assertIsNone(result)
