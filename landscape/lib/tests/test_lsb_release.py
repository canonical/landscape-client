import unittest
from subprocess import CalledProcessError
from unittest import mock

from landscape.lib import testing
from landscape.lib.lsb_release import parse_lsb_release


class LsbReleaseTest(testing.FSTestCase, unittest.TestCase):
    def test_parse_lsb_release(self):
        with mock.patch("landscape.lib.lsb_release.check_output") as co_mock:
            co_mock.return_value = (
                b"Ubuntu\nUbuntu 22.04.1 LTS\n22.04\njammy\n"
            )
            lsb_release = parse_lsb_release()

        self.assertEqual(
            lsb_release,
            {
                "distributor-id": "Ubuntu",
                "description": "Ubuntu 22.04.1 LTS",
                "release": "22.04",
                "code-name": "jammy",
            },
        )

    def test_parse_lsb_release_debian(self):
        with mock.patch("landscape.lib.lsb_release.check_output") as co_mock:
            co_mock.return_value = (
                b"Debian\nDebian GNU/Linux 11 (bullseye)\n11\nbullseye\n"
            )
            lsb_release = parse_lsb_release()

        self.assertEqual(
            lsb_release,
            {
                "distributor-id": "Debian",
                "description": "Debian GNU/Linux 11 (bullseye)",
                "release": "11",
                "code-name": "bullseye",
            },
        )

    def test_parse_lsb_release_file(self):
        """
        L{parse_lsb_release} returns a C{dict} holding information from
        the given LSB release file.
        """
        lsb_release_filename = self.makeFile(
            "DISTRIB_ID=Ubuntu\n"
            "DISTRIB_RELEASE=6.06\n"
            "DISTRIB_CODENAME=dapper\n"
            "DISTRIB_DESCRIPTION="
            '"Ubuntu 6.06.1 LTS"\n',
        )

        with mock.patch("landscape.lib.lsb_release.check_output") as co_mock:
            co_mock.side_effect = CalledProcessError(127, "")
            lsb_release = parse_lsb_release(lsb_release_filename)

        self.assertEqual(
            lsb_release,
            {
                "distributor-id": "Ubuntu",
                "description": "Ubuntu 6.06.1 LTS",
                "release": "6.06",
                "code-name": "dapper",
            },
        )

    def test_parse_lsb_release_file_with_missing_or_extra_fields(self):
        """
        L{parse_lsb_release} ignores lines not matching the map of
        known keys, and returns only keys with an actual value.
        """
        lsb_release_filename = self.makeFile("DISTRIB_ID=Ubuntu\nFOO=Bar\n")

        with mock.patch("landscape.lib.lsb_release.check_output") as co_mock:
            co_mock.side_effect = CalledProcessError(127, "")
            lsb_release = parse_lsb_release(lsb_release_filename)

        self.assertEqual(lsb_release, {"distributor-id": "Ubuntu"})

    def test_parse_lsb_release_file_not_found(self):
        with mock.patch("landscape.lib.lsb_release.check_output") as co_mock:
            co_mock.side_effect = CalledProcessError(127, "")

            self.assertRaises(
                FileNotFoundError,
                parse_lsb_release,
                "TheresNoWayThisFileExists",
            )
