import unittest
from unittest import mock

from landscape.lib import testing
from landscape.lib.os_release import parse_os_release

SAMPLE_OS_RELEASE = """PRETTY_NAME="Ubuntu 22.04.3 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.3 LTS (Jammy Jellyfish)"
VERSION_CODENAME=codename
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=codename
"""


class OsReleaseTest(testing.FSTestCase, unittest.TestCase):
    def test_parse_os_release(self):
        """
        L{parse_os_release} ignores lines not matching the map of
        known keys, and returns only keys with an actual value. By
        default it reads from OS_RELEASE_FILENAME if no other path
        is provided.
        """

        os_release_filename = self.makeFile(SAMPLE_OS_RELEASE)

        with mock.patch(
            "landscape.lib.os_release.OS_RELEASE_FILENAME",
            new=os_release_filename,
        ):
            os_release = parse_os_release()

        self.assertEqual(
            os_release,
            {
                "code-name": "codename",
                "description": "Ubuntu 22.04.3 LTS",
                "distributor-id": "Ubuntu",
                "release": "22.04",
            },
        )

    def test_parse_os_release_no_etc(self):
        """
        L{parse_os_release} ignores lines not matching the map of
        known keys, and returns only keys with an actual value. By
        default it reads from OS_RELEASE_FILENAME if no other path
        is provided and it should read from SAMPLE_OS_RELEASE_FALLBACK
        path if there OS_RELEASE_FILENAME doesn't exists.
        """

        os_release_filename = self.makeFile(SAMPLE_OS_RELEASE)

        with mock.patch("os.path.exists") as co_mock:
            co_mock.return_value = False

            with mock.patch(
                "landscape.lib.os_release.OS_RELEASE_FILENAME_FALLBACK",
                new=os_release_filename,
            ):
                os_release = parse_os_release()

        self.assertEqual(
            os_release,
            {
                "code-name": "codename",
                "description": "Ubuntu 22.04.3 LTS",
                "distributor-id": "Ubuntu",
                "release": "22.04",
            },
        )

    def test_parse_os_release_no_perms(self):
        """
        L{parse_os_release} ignores lines not matching the map of
        known keys, and returns only keys with an actual value. By
        default it reads from OS_RELEASE_FILENAME if no other path
        is provided and it should read from SAMPLE_OS_RELEASE_FALLBACK
        path if there OS_RELEASE_FILENAME is not readable.
        """

        os_release_filename = self.makeFile(SAMPLE_OS_RELEASE)

        with mock.patch("os.access") as co_mock:
            co_mock.return_value = False

            with mock.patch(
                "landscape.lib.os_release.OS_RELEASE_FILENAME_FALLBACK",
                new=os_release_filename,
            ):
                os_release = parse_os_release()

        self.assertEqual(
            os_release,
            {
                "code-name": "codename",
                "description": "Ubuntu 22.04.3 LTS",
                "distributor-id": "Ubuntu",
                "release": "22.04",
            },
        )

    def test_parse_os_release_with_file(self):
        """
        L{parse_os_release} returns a C{dict} holding information from
        the given OS release file.
        """
        os_release_filename = self.makeFile(SAMPLE_OS_RELEASE)
        os_release = parse_os_release(os_release_filename)

        self.assertEqual(
            os_release,
            {
                "distributor-id": "Ubuntu",
                "description": "Ubuntu 22.04.3 LTS",
                "release": "22.04",
                "code-name": "codename",
            },
        )

    def test_parse_os_release_with_file_not_found(self):
        """
        L{parse_os_release} should fail with FileNotFound
        if given OS release file doesn't exists.
        """

        self.assertRaises(
            FileNotFoundError,
            parse_os_release,
            "TheresNoWayThisFileExists",
        )
