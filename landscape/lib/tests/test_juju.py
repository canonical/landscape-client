from collections import namedtuple
import json

from landscape.tests.helpers import LandscapeTest
from landscape.lib.juju import get_juju_info


SAMPLE_JUJU_INFO = json.dumps({"environment-uuid": "DEAD-BEEF",
                               "unit-name": "juju-unit-name",
                               "api-addresses": "10.0.3.1:17070",
                               "private-address": "127.0.0.1"})


class JujuTest(LandscapeTest):

    Config = namedtuple("Config", "juju_filename")

    def test_get_juju_info_sample_data(self):
        stub_config = self.Config(self.makeFile(SAMPLE_JUJU_INFO))
        juju_info = get_juju_info(stub_config)
        self.assertEqual("DEAD-BEEF", juju_info["environment-uuid"])
        self.assertEqual("juju-unit-name", juju_info["unit-name"])
        self.assertEqual("10.0.3.1:17070", juju_info["api-addresses"])
        self.assertEqual("127.0.0.1", juju_info["private-address"])

    def test_get_juju_info_empty_file(self):
        stub_config = self.Config(self.makeFile(""))
        juju_info = get_juju_info(stub_config)
        self.log_helper.ignore_errors(ValueError)
        self.assertEqual(juju_info, None)
        self.assertTrue(
            "Error attempting to read JSON" in self.logfile.getvalue())

    def test_get_juju_info_not_a_file(self):
        stub_config = self.Config("/")
        juju_info = get_juju_info(stub_config)
        self.assertEqual(juju_info, None)
