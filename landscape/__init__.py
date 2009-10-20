DEBIAN_REVISION = ""
UPSTREAM_VERSION = "1.3.2.1"
VERSION = "%s%s" % (UPSTREAM_VERSION, DEBIAN_REVISION)
API = "3.2"

from twisted.python import util


def initgroups(uid, gid):
    import pwd
    from landscape.lib.initgroups import initgroups as cinitgroups
    return cinitgroups(pwd.getpwuid(uid).pw_name, gid)

# Patch twisted initgroups implementation, which can result in very long calls
# to grp.getrlall()
util.initgroups = initgroups
