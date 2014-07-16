"""Helpers for dealing with software versioning."""


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
    return _version_to_tuple(version1) >= _version_to_tuple(version2)


def sort_versions(versions):
    """Sort a list of software versions from the highest to the lowest."""
    tuples = [_version_to_tuple(version) for version in versions]
    return [_tuple_to_version(tuple) for tuple in sorted(tuples, reverse=True)]


def _version_to_tuple(version):
    """Convert a version string to a tuple of integers."""
    return tuple(map(int, version.split(".")))


def _tuple_to_version(tuple):
    """Convert a tuple of integers to a version string."""
    return ".".join(map(str, tuple))
