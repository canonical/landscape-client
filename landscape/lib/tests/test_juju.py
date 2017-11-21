from collections import namedtuple
import json
import unittest

from landscape.lib import testing
from landscape.lib.juju import get_juju_info


SAMPLE_JUJU_INFO = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "machine-id": "1",
                               "api-addresses": "10.0.3.1:17070",
                               "private-address": "127.0.0.1"})

SAMPLE_JUJU_INFO_2 = json.dumps({"environment-uuid": "DEAD-BEEF",
                                 "machine-id": "1",
                                 "api-addresses": "10.0.3.2:17070",
                                 "private-address": "127.0.0.1"})


class JujuTest(testing.HelperTestCase, testing.FSTestCase, unittest.TestCase):

    Config = namedtuple("Config", ["juju_filename"])

    def setUp(self):
        super(JujuTest, self).setUp()
        self.stub_config = self.Config(self.makeFile())

    def _create_tmp_juju_file(self, contents):
        return self.makeFile(
            contents, path=self.stub_config.juju_filename)

    def test_get_juju_info(self):
        """
        L{get_juju_info} parses JSON data from the juju_filename file.
        """
        self._create_tmp_juju_file(SAMPLE_JUJU_INFO)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual(
            {u"environment-uuid": "DEAD-BEEF",
             u"machine-id": "1",
             u"private-address": "127.0.0.1",
             u"api-addresses": ["10.0.3.1:17070"]}, juju_info)

    def test_get_juju_info_empty_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        an empty file, it returns C{None}.
        """
        self.log_helper.ignore_errors(ValueError)
        self._create_tmp_juju_file("")
        self.assertIs(None, get_juju_info(self.stub_config))
        self.assertIn("Error attempting to read JSON", self.logfile.getvalue())

    def test_get_juju_info_no_json_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        a directory containing no json files, it returns None.
        """
        self.assertIs(None, get_juju_info(self.stub_config))

    def test_get_juju_info_multiple_endpoints(self):
        """L{get_juju_info} turns space separated API addresses into a list."""
        juju_multiple_endpoints = json.dumps({
            "environment-uuid": "DEAD-BEEF",
            "machine-id": "0",
            "api-addresses": "10.0.3.1:17070 10.0.3.2:18080",
            "private-address": "127.0.0.1"})

        self._create_tmp_juju_file(juju_multiple_endpoints)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual(
            {"environment-uuid": "DEAD-BEEF",
             "machine-id": "0",
             "api-addresses": ["10.0.3.1:17070", "10.0.3.2:18080"],
             "private-address": "127.0.0.1"}, juju_info)
