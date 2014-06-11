from collections import namedtuple
import json

from landscape.tests.helpers import LandscapeTest
from landscape.lib.juju import get_juju_info


SAMPLE_JUJU_INFO = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "unit-name": "service/0",
                               "api-addresses": "10.0.3.1:17070",
                               "private-address": "127.0.0.1"})

SAMPLE_JUJU_INFO_2 = json.dumps({"environment-uuid": "DEAD-BEEF",
                                 "unit-name": "service-2/0",
                                 "api-addresses": "10.0.3.2:17070",
                                 "private-address": "127.0.0.1"})


class JujuTest(LandscapeTest):

    Config = namedtuple("Config", ["juju_directory", "juju_filename"])

    def setUp(self):
        super(JujuTest, self).setUp()
        self.stub_config = self.Config(self.makeDir(), "")

    def _create_tmp_juju_file(self, contents):
        return self.makeFile(
            contents, dirname=self.stub_config.juju_directory, suffix=".json")

    def test_get_juju_info_sample_data(self):
        """L{get_juju_info} parses JSON data from the '*.json' files in the
        juju_directory. A single file is present."""
        self._create_tmp_juju_file(SAMPLE_JUJU_INFO)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual([
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070"],
             u"private-address": "127.0.0.1"}], juju_info)

    def test_get_juju_info_sample_data_legacy_file(self):
        """L{get_juju_info} parses JSON data from the 'juju-info.json' file in
        the data direectory, to remain compatible with older versions of the
        landscape-client charm."""
        self.stub_config = self.Config(self.makeDir(), self.makeFile(
            content=SAMPLE_JUJU_INFO, basename="juju-info", suffix=".json"))
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual([
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070"],
             u"private-address": "127.0.0.1"}], juju_info)

    def test_get_juju_info_two_sample_data(self):
        """
        L{get_juju_info} parses JSON data from the '*.json' files in the
        juju_directory. A two files are present.
        """
        self._create_tmp_juju_file(SAMPLE_JUJU_INFO)
        self._create_tmp_juju_file(SAMPLE_JUJU_INFO_2)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual([
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service-2/0",
             u"api-addresses": ["10.0.3.2:17070"],
             u"private-address": "127.0.0.1"},
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070"],
             u"private-address": "127.0.0.1"}], juju_info)

    def test_get_juju_info_ignores_non_json(self):
        """
        A file that doesn't end in *.json in the juju_directory is ignored.
        """
        self._create_tmp_juju_file(SAMPLE_JUJU_INFO)
        self.makeFile(SAMPLE_JUJU_INFO_2, suffix=".txt",
                      dirname=self.stub_config.juju_directory)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual([
            {u"environment-uuid": "DEAD-BEEF",
             u"unit-name": "service/0",
             u"api-addresses": ["10.0.3.1:17070"],
             u"private-address": "127.0.0.1"}], juju_info)

    def test_get_juju_info_empty_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        an empty file, it returns C{None}.
        """
        self._create_tmp_juju_file("")
        juju_info = get_juju_info(self.stub_config)
        self.log_helper.ignore_errors(ValueError)
        self.assertEqual(juju_info, None)
        self.assertIn("Error attempting to read JSON", self.logfile.getvalue())

    def test_get_juju_info_no_json_file(self):
        """
        If L{get_juju_info} is called with a configuration pointing to
        a directory containing no json files, it returns None.
        """
        juju_info = get_juju_info(self.stub_config)
        self.assertIs(juju_info, None)

    def test_get_juju_info_multiple_endpoints(self):
        """L{get_juju_info} turns space separated API addresses into a list."""
        juju_multiple_endpoints = json.dumps({
                "environment-uuid": "DEAD-BEEF",
                "unit-name": "service/0",
                "api-addresses": "10.0.3.1:17070 10.0.3.2:18080",
                "private-address": "127.0.0.1"})

        self._create_tmp_juju_file(juju_multiple_endpoints)
        juju_info = get_juju_info(self.stub_config)
        self.assertEqual([
            {"environment-uuid": "DEAD-BEEF",
             "unit-name": "service/0",
             "api-addresses": ["10.0.3.1:17070", "10.0.3.2:18080"],
             "private-address": "127.0.0.1"}], juju_info)
