"""Helpers for dealing with software versioning."""

from distutils.version import StrictVersion


def compare_versions(version1, version2):
    """Compare two software versions.

    This takes the two software versions of the usual "y.x" form
    and split them on the decimal character, converting both parts
    to ints, e.g. "3.2" becomes (3, 2).

    It then does a comparison of the two tuples, and returns C{True} if
    C{version1} is greater than or equal to C{version2}.

    @param version1: The first version to compare.
    @param version2: The second version to compare.
    @return: C{True} if the first version is greater than or equal to
        the second.
    """
    return StrictVersion(version1) >= StrictVersion(version2)


def sort_versions(versions):
    """Sort a list of software versions from the highest to the lowest."""
    return sorted(
        [StrictVersion(version) for version in versions], reverse=True)
