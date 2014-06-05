from collections import namedtuple
import json

from landscape.tests.helpers import LandscapeTest
from landscape.lib.juju import get_juju_info


SAMPLE_JUJU_INFO = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "unit-name": "service/0",
                               "api-addresses": "10.0.3.1:17070",
                               "private-address": "127.0.0.1"})


class JujuTest(LandscapeTest):

    Config = namedtuple("Config", "juju_filename")

    def test_get_juju_info_sample_data(self):
        """L{get_juju_info} parses JSON data from the juju_filename file."""
        stub_config = self.Config(self.makeFile(SAMPLE_JUJU_INFO))
        juju_info = get_juju_info(stub_config)
        self.assertEqual(
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070"],
             u"private-address": "127.0.0.1"}, juju_info)

    def test_get_juju_info_empty_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        an empty file, it returns C{None}.
        """
        stub_config = self.Config(self.makeFile(""))
        juju_info = get_juju_info(stub_config)
        self.log_helper.ignore_errors(ValueError)
        self.assertEqual(juju_info, None)
        self.assertIn("Error attempting to read JSON", self.logfile.getvalue())

    def test_get_juju_info_not_a_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        a directory, it returns C{None}.
        """
        stub_config = self.Config("/")
        juju_info = get_juju_info(stub_config)
        self.assertIs(juju_info, None)

    def test_get_juju_info_multiple_endpoints(self):
        """L{get_juju_info} turns space separated API addresses into a list."""
        juju_multiple_endpoints = json.dumps({
                "environment-uuid": "DEAD-BEEF",
                "unit-name": "service/0",
                "api-addresses": "10.0.3.1:17070 10.0.3.2:18080",
                "private-address": "127.0.0.1"})

        stub_config = self.Config(self.makeFile(juju_multiple_endpoints))
        juju_info = get_juju_info(stub_config)
        self.assertEqual(
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070", "10.0.3.2:18080"],
             u"private-address": "127.0.0.1"}, juju_info)
