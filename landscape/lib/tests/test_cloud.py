import unittest

from landscape.lib import testing
from landscape.lib.cloud import (
    EC2_API, _fetch_ec2_item, fetch_ec2_meta_data, MAX_LENGTH)
from landscape.lib.fetch import HTTPCodeError, PyCurlError
from twisted.internet.defer import succeed, fail


class CloudTest(testing.HelperTestCase, testing.TwistedTestCase,
                unittest.TestCase):

    def setUp(self):
        super(CloudTest, self).setUp()
        self.query_results = {}
        self.kwargs = {}

        def fetch_stub(url, **kwargs):
            self.kwargs = kwargs
            value = self.query_results[url]
            if isinstance(value, Exception):
                return fail(value)
            else:
                return succeed(value)

        self.fetch_func = fetch_stub
        self.add_query_result("instance-id", b"i00001")
        self.add_query_result("ami-id", b"ami-00002")
        self.add_query_result("instance-type", b"hs1.8xlarge")

    def add_query_result(self, name, value):
        """
        Add a url to self.query_results that is then available through
        self.fetch_func. C{value} must be bytes or an Error as the original
        fetch returns bytes.
        """
        url = "%s/meta-data/%s" % (EC2_API, name)
        self.query_results[url] = value

    def test_fetch_ec2_meta_data_error_on_any_item_error(self):
        """
        L{_fetch_ec2_meta_data} returns a deferred C{Failure} containing the
        error message when an error occurs on any of the queried meta-data
        items C{instance-id}, C{ami-id} or C{instance-type}.
        """
        self.log_helper.ignore_errors(HTTPCodeError)
        error = HTTPCodeError(404, "notfound")
        metadata_items = ["instance-id", "ami-id", "instance-type"]
        for item in metadata_items:
            # reset all item data adding the error to only 1 item per iteration
            for setup_item in metadata_items:
                if setup_item == item:
                    self.add_query_result(item, error)
                else:
                    self.add_query_result(setup_item, "value%s" % setup_item)

            deferred = fetch_ec2_meta_data(fetch=self.fetch_func)
            failure = self.failureResultOf(deferred)
            self.assertEqual(
                "Server returned HTTP code 404",
                failure.getErrorMessage())

    def test_fetch_ec2_meta_data(self):
        """
        L{_fetch_ec2_meta_data} returns a C{dict} containing meta-data for
        C{instance-id}, C{ami-id} and C{instance-type}.
        """
        deferred = fetch_ec2_meta_data(fetch=self.fetch_func)
        result = self.successResultOf(deferred)
        self.assertEqual(
            {"ami-id": u"ami-00002",
             "instance-id": u"i00001",
             "instance-type": u"hs1.8xlarge"},
            result)

    def test_fetch_ec2_meta_data_utf8(self):
        """
        L{_fetch_ec2_meta_data} decodes utf-8 byte strings returned from the
        external service.
        """
        self.add_query_result("ami-id", b"asdf\xe1\x88\xb4")
        deferred = fetch_ec2_meta_data(fetch=self.fetch_func)
        result = self.successResultOf(deferred)
        self.assertEqual({"instance-id": u"i00001",
                          "ami-id": u"asdf\u1234",
                          "instance-type": u"hs1.8xlarge"},
                         result)

    def test_fetch_ec2_meta_data_truncates(self):
        """L{_fetch_ec2_meta_data} truncates values that are too long."""
        self.add_query_result("ami-id", b"a" * MAX_LENGTH * 5)
        self.add_query_result("instance-id", b"b" * MAX_LENGTH * 5)
        self.add_query_result("instance-type", b"c" * MAX_LENGTH * 5)
        deferred = fetch_ec2_meta_data(fetch=self.fetch_func)
        result = self.successResultOf(deferred)
        self.assertEqual(
            {"ami-id": "a" * MAX_LENGTH,
             "instance-id": "b" * MAX_LENGTH,
             "instance-type": "c" * MAX_LENGTH},
            result)

    def test_wb_fetch_ec2_item_multiple_items_appends_accumulate_list(self):
        """
        L{_fetch_ec2_item} retrieves individual meta-data items from the
        EC2 api and appends them to the C{list} provided by the C{accumulate}
        parameter.
        """
        accumulate = []
        self.successResultOf(
            _fetch_ec2_item("instance-id", accumulate, fetch=self.fetch_func))
        self.successResultOf(
            _fetch_ec2_item(
                "instance-type", accumulate, fetch=self.fetch_func))
        self.assertEqual([b"i00001", b"hs1.8xlarge"], accumulate)

    def test_wb_fetch_ec2_item_error_returns_failure(self):
        """
        L{_fetch_ec2_item} returns a deferred C{Failure} containing the error
        message when faced with no EC2 cloud API service.
        """
        self.log_helper.ignore_errors(PyCurlError)
        self.add_query_result("other-id", PyCurlError(60, "pycurl error"))
        accumulate = []
        deferred = _fetch_ec2_item(
            "other-id", accumulate, fetch=self.fetch_func)
        failure = self.failureResultOf(deferred)
        self.assertEqual("Error 60: pycurl error", failure.getErrorMessage())

    def test_wb_fetch_ec2_meta_data_nofollow(self):
        """
        L{_fetch_ec2_meta_data} sets C{follow} to C{False} to avoid following
        HTTP redirects.
        """
        self.log_helper.ignore_errors(PyCurlError)
        self.add_query_result("other-id", PyCurlError(60, "pycurl error"))
        accumulate = []
        deferred = _fetch_ec2_item(
            "other-id", accumulate, fetch=self.fetch_func)
        self.failureResultOf(deferred)
        self.assertEqual({"follow": False}, self.kwargs)
