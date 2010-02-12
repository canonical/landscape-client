DEBIAN_REVISION = "-0ubuntu0.9.10.0"
UPSTREAM_VERSION = "1.4.0"
VERSION = "%s%s" % (UPSTREAM_VERSION, DEBIAN_REVISION)
API = "3.2"

from twisted.python import util


def initgroups(uid, gid):
    """Initializes the group access list.

    It replaces the default implementation of Twisted which iterates other all
    groups, using the system call C{initgroups} instead. This wrapper just
    translates the numeric C{uid} to a user name understood by C{initgroups}.
    """
    import pwd
    from landscape.lib.initgroups import initgroups as cinitgroups
    return cinitgroups(pwd.getpwuid(uid).pw_name, gid)

# Patch twisted initgroups implementation, which can result in very long calls
# to grp.getrlall(). See http://twistedmatrix.com/trac/ticket/3226
util.initgroups = initgroups
