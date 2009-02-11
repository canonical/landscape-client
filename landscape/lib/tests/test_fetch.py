import pycurl

from landscape.lib.fetch import fetch, fetch_async
from landscape.tests.helpers import LandscapeTest


class CurlStub(object):

    def __init__(self, result=None):
        self.options = {}
        self.performed = False
        self.result = result

    def setopt(self, option, value):
        if self.performed:
            raise AssertionError("setopt() can't be called after perform()")
        self.options[option] = value

    def perform(self):
        if self.performed:
            raise AssertionError("Can't perform twice")
        self.options[pycurl.WRITEFUNCTION](self.result)
        self.performed = True


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
                           pycurl.WRITEFUNCTION: Any()})

    def test_post(self):
        curl = CurlStub("result")
        result = fetch("http://example.com", post=True, curl=curl)
        self.assertEquals(result, "result")
        self.assertEquals(curl.options,
                          {pycurl.URL: "http://example.com",
                           pycurl.FOLLOWLOCATION: True,
                           pycurl.MAXREDIRS: 5,
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
                           pycurl.WRITEFUNCTION: Any(),
                           pycurl.HTTPHEADER: ["a: 1", "b: 2"]})

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
                               pycurl.WRITEFUNCTION: Any()})
        finally:
            pycurl.Curl = Curl

    def test_async_fetch(self):
        curl = CurlStub("result")
        d = fetch_async("http://example.com/", curl=curl)
        def got_result(result):
            self.assertEquals(result, "result")
        return d.addCallback(got_result)

