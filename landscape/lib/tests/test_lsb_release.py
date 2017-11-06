import unittest

from landscape.lib import testing
from landscape.lib.lsb_release import parse_lsb_release


class LsbReleaseTest(testing.FSTestCase, unittest.TestCase):

    def test_parse_lsb_release(self):
        """
        L{parse_lsb_release} returns a C{dict} holding information from
        the given LSB release file.
        """
        lsb_release_filename = self.makeFile("DISTRIB_ID=Ubuntu\n"
                                             "DISTRIB_RELEASE=6.06\n"
                                             "DISTRIB_CODENAME=dapper\n"
                                             "DISTRIB_DESCRIPTION="
                                             "\"Ubuntu 6.06.1 LTS\"\n")

        self.assertEqual(parse_lsb_release(lsb_release_filename),
                         {"distributor-id": "Ubuntu",
                          "description": "Ubuntu 6.06.1 LTS",
                          "release": "6.06",
                          "code-name": "dapper"})

    def test_parse_lsb_release_with_missing_or_extra_fields(self):
        """
        L{parse_lsb_release} ignores lines not matching the map of
        known keys, and returns only keys with an actual value.
        """
        lsb_release_filename = self.makeFile("DISTRIB_ID=Ubuntu\n"
                                             "FOO=Bar\n")
        self.assertEqual(parse_lsb_release(lsb_release_filename),
                         {"distributor-id": "Ubuntu"})
