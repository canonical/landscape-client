import os

import pycurl

from landscape.lib.fetch import (
    fetch, fetch_async, fetch_many_async, fetch_to_files,
    HTTPCodeError, PyCurlError)
from landscape.tests.helpers import LandscapeTest


class CurlStub(object):

    def __init__(self, result=None, http_code=200, error=None):
        self.result = result
        self._http_code = http_code
        self.options = {}
        self.performed = False
        self.error = error

    def getinfo(self, what):
        if what == pycurl.HTTP_CODE:
            return self._http_code
        raise RuntimeError("Stub doesn't know about %d info" % what)

    def setopt(self, option, value):
        if isinstance(value, unicode):
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

class CurlManyStub(object):

    def __init__(self, results):
        self.curls = []
        for result in results:
            if isinstance(result, str):
                body = result
                http_code = 200
            else:
                body = result[0]
                http_code = result[1]
            self.curls.append(CurlStub(body, http_code=http_code))
        self.count = 0

    def getinfo(self, what):
        if not self.curls[self.count].performed:
            raise AssertionError("getinfo() can't be called before perform()")
        result = self.curls[self.count].getinfo(what)
        self.count += 1
        return result
        
    def setopt(self, option, value):
        self.curls[self.count].setopt(option, value)

    def perform(self):
        self.curls[self.count].perform()

class Any(object):
    def __eq__(self, other):
        return True


class FetchTest(LandscapeTest):

    def test_basic(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 30,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 600,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any()})

    def test_post(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", post=True, curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 30,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 600,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any(),
                           pycurl.POST: True})

    def test_post_data(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", post=True, data="data", curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options[pycurl.READFUNCTION](), "data")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 30,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 600,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any(),
                           pycurl.POST: True,
                           pycurl.POSTFIELDSIZE: 4,
                           pycurl.READFUNCTION: Any()})

    def test_cainfo(self):
        curl = CurlStub("result")
        result = fetch("https://example.com", cainfo="cainfo", curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "https://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 30,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 600,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any(),
                           pycurl.CAINFO: "cainfo"})

    def test_cainfo_on_http(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", cainfo="cainfo", curl=curl)
        self.assertEquals(result, "result")
        self.assertTrue(pycurl.CAINFO not in curl.options)

    def test_headers(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", headers={"a":"1", "b":"2"},
                       curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 30,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 600,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any(),
                           pycurl.HTTPHEADER: ["a: 1", "b: 2"]})

    def test_timeouts(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", connect_timeout=5, total_timeout=30,
                       curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
                           pycurl.CONNECTTIMEOUT: 5,
                           pycurl.LOW_SPEED_LIMIT: 1,
                           pycurl.LOW_SPEED_TIME: 30,
                           pycurl.NOSIGNAL: 1,
                           pycurl.WRITEFUNCTION: Any()})

    def test_unicode(self):
        """
        The L{fetch} function converts the C{url} parameter to C{str} before
        passing it to curl.
        """
        curl = CurlStub("result")
        result = fetch(u"http://example.com", curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options[pycurl.URL], "http://example.com")
        self.assertTrue(isinstance(curl.options[pycurl.URL], str))

    def test_non_200_result(self):
        curl = CurlStub("result", http_code=404)
        try:
            fetch("http://example.com", curl=curl)
        except HTTPCodeError, error:
            self.assertEquals(error.http_code, 404)
            self.assertEquals(error.body, "result")
        else:
            self.fail("HTTPCodeError not raised")

    def test_http_error_str(self):
        self.assertEquals(str(HTTPCodeError(501, "")),
                          "Server returned HTTP code 501")

    def test_http_error_repr(self):
        self.assertEquals(repr(HTTPCodeError(501, "")),
                          "<HTTPCodeError http_code=501>")

    def test_pycurl_error(self):
        curl = CurlStub(result=None, http_code=None,
                        error=pycurl.error(60, "pycurl error"))
        try:
            fetch("http://example.com", curl=curl)
        except PyCurlError, error:
            self.assertEquals(error.error_code, 60)
            self.assertEquals(error.message, "pycurl error")
        else:
            self.fail("PyCurlError not raised")

    def test_pycurl_error_str(self):
        self.assertEquals(str(PyCurlError(60, "pycurl error")),
                          "Error 60: pycurl error")

    def test_pycurl_error_repr(self):
        self.assertEquals(repr(PyCurlError(60, "pycurl error")),
                          "<PyCurlError args=(60, 'pycurl error')>")

    def test_create_curl(self):
        curls = []
        def pycurl_Curl():
            curl = CurlStub("result")
            curls.append(curl)
            return curl
        Curl = pycurl.Curl
        try:
            pycurl.Curl = pycurl_Curl
            result = fetch("http://example.com")
            curl = curls[0]
            self.assertEquals(result, "result")
            self.assertEquals(curl.options,
                              {pycurl.URL: "http://example.com",
                               pycurl.FOLLOWLOCATION: True,
                               pycurl.MAXREDIRS: 5,
                               pycurl.CONNECTTIMEOUT: 30,
                               pycurl.LOW_SPEED_LIMIT: 1,
                               pycurl.LOW_SPEED_TIME: 600,
                               pycurl.NOSIGNAL: 1,
                               pycurl.WRITEFUNCTION: Any()})
        finally:
            pycurl.Curl = Curl

    def test_async_fetch(self):
        curl = CurlStub("result")
        d = fetch_async("http://example.com/", curl=curl)
        def got_result(result):
            self.assertEquals(result, "result")
        return d.addCallback(got_result)

    def test_async_fetch_with_error(self):
        curl = CurlStub("result", http_code=501)
        d = fetch_async("http://example.com/", curl=curl)
        def got_error(failure):
            self.assertEquals(failure.value.http_code, 501)
            self.assertEquals(failure.value.body, "result")
            return failure
        d.addErrback(got_error)
        self.assertFailure(d, HTTPCodeError)
        return d

    def test_fetch_many_async(self):
        """
        L{fetch_many_async} retrives multiple URLs, and returns a C{DeferredList}
        firing its callback when all the URLs have successfully completed.
        """
        urls = ["http://good/", "http://better/"]
        results = ["good", "better"]

        def callback(result, url):
            self.assertIn(result, results)
            self.assertIn(url, urls)
            urls.remove(url)
            results.remove(result)

        def errback(failure, url):
            self.fail()

        curl = CurlManyStub(results)
        d = fetch_many_async(urls, callback=callback, errback=errback,
                             curl=curl)

        def completed(result):
            self.assertEquals(curl.count, 2)
            self.assertEquals(urls, [])
            self.assertEquals(results, [])

        return d.addCallback(completed)

    def test_fetch_many_async_with_error(self):
        """
        L{fetch_many_async} aborts as soon as one URL fails.
        """
        urls = ["http://right/", "http://wrong/", "http://impossilbe/"]
        results = ["right", ("wrong", 501), "impossible"]
        fetched_urls = []

        def callback(result, url):
            fetched_urls.append(url)

        def errback(failure, url):
            fetched_urls.append(url)
            self.assertEquals(failure.value.body, "wrong")
            self.assertEquals(failure.value.http_code, 501)
            return failure
    
        curl = CurlManyStub(results)
        d = fetch_many_async(urls, callback=callback, errback=errback,
                             curl=curl)

        def completed(result):
            self.fail()

        def aborted(failure):
            self.assertEquals(fetched_urls, ["http://right/", "http://wrong/"])

        d.addCallback(completed)
        d.addErrback(aborted)
        return d

    def test_fetch_to_files(self):
        """
        L{fetch_to_files} fetches a list of URLs and save they're content
        in the given directory.
        """
        urls = ["http://good/file", "http://even/better-file"]
        results = ["file", "better-file"]
        directory = self.makeDir()
        curl = CurlManyStub(results)

        result = fetch_to_files(urls, directory, curl=curl)

        def check_files(ignored):
            for result in results:
                fd = open(os.path.join(directory, result))
                self.assertEquals(fd.read(), result)
                fd.close()

        result.addCallback(check_files)
        return result

    def test_fetch_to_files_with_errors(self):
        """
        L{fetch_to_files} optionally logs an error message as soon as one URL
        fails, and aborts.
        """
        urls = ["http://im/right", "http://im/wrong", "http://im/not"]
        results = ["right", ("wrong", 404), "not"]
        directory = self.makeDir()
        messages = []
        logger = lambda message: messages.append(message)
        curl = CurlManyStub(results)

        result = fetch_to_files(urls, directory, logger=logger, curl=curl)

        def check_messages(failure):
            self.assertEquals(len(messages), 1)
            self.assertEquals(messages[0],
                              "Couldn't fetch file from http://im/wrong "
                              "(Server returned HTTP code 404)")
            messages.pop()

        def check_files(ignored):
            self.assertEquals(messages, [])
            self.assertTrue(os.path.exists(os.path.join(directory, "right")))
            self.assertFalse(os.path.exists(os.path.join(directory, "not")))

        result.addErrback(check_messages)
        result.addCallback(check_files)
        return result

    def test_fetch_to_files_with_non_existing_directory(self):
        """
        The deferred list returned by L{fetch_to_files} results in a failure
        if the destination directory doesn't exist.
        """
        urls = ["http://im/right", "http://im/good"]
        results = ["right", "good"]
        directory = "i/dont/exist/"
        curl = CurlManyStub(results)

        result = fetch_to_files(urls, directory, curl=curl)

        def check_error(failure):
            error = str(failure.value.subFailure.value)
            self.assertEquals(error, "[Errno 2] No such file or directory: "
                              "'i/dont/exist/right'")
            self.assertFalse(os.path.exists(os.path.join(directory, "right")))
            self.assertFalse(os.path.exists(os.path.join(directory, "good")))

        result.addErrback(check_error)
        return result
