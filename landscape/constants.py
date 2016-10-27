"""
Hold constants used across landscape, to reduce import size when one only needs
to look at those values.
"""

APT_PREFERENCES_SIZE_LIMIT = 1048576  # 1 MByte

# The name "UBUNTU" is used in the variable name due to the fact that the path
# is Ubuntu-specific, taken from /etc/login.defs.
UBUNTU_PATH = ":".join(
    ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin",
     "/bin", "/snap/bin"])

SUCCESS_RESULT = 1
ERROR_RESULT = 100
DEPENDENCY_ERROR_RESULT = 101
CLIENT_VERSION_ERROR_RESULT = 102
POLICY_STRICT = 0
POLICY_ALLOW_INSTALLS = 1
POLICY_ALLOW_ALL_CHANGES = 2

# The amount of time to wait while we have unknown package data before
# reporting an error to the server in response to an operation.
# The two common cases of this are:
# 1.  The server requested an operation that we've decided requires some
# dependencies, but we don't know the package ID of those dependencies.  It
# should only take a bit more than 10 minutes for that to be resolved by the
# package reporter.
# 2.  We lost some package data, for example by a deb archive becoming
# inaccessible for a while.  The earliest we can reasonably assume that to be
# resolved is in 60 minutes, when the package reporter runs again.

# So we'll give the problem one chance to resolve itself, by only waiting for
# one run of apt-update.
UNKNOWN_PACKAGE_DATA_TIMEOUT = 70 * 60
