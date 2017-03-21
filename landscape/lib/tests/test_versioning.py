from unittest import TestCase

from landscape.lib.versioning import is_version_higher, sort_versions


class IsVersionHigherTest(TestCase):

    def test_greater(self):
        """
        The C{is_version_higher} function returns C{True} if the first
        version is greater than the second.
        """
        self.assertTrue(is_version_higher(b"3.2", b"3.1"))

    def test_equal(self):
        """
        The C{is_version_higher} function returns C{True} if the first
        version is the same as the second.
        """
        self.assertTrue(is_version_higher(b"3.1", b"3.1"))

    def test_lower(self):
        """
        The C{is_version_higher} function returns C{False} if the first
        version is lower than the second.
        """
        self.assertFalse(is_version_higher(b"3.1", b"3.2"))


class SortVersionsTest(TestCase):

    def test_sort(self):
        """
        The C{sort_versions} function sorts the given versions from the
        highest to the lowest.
        """
        versions = [b"3.2", b"3.3", b"3.1"]
        self.assertEqual([b"3.3", b"3.2", b"3.1"], sort_versions(versions))
