DEBIAN_REVISION = ""
UPSTREAM_VERSION = "1.4.4"
VERSION = "%s%s" % (UPSTREAM_VERSION, DEBIAN_REVISION)

# The "server-api" field of outgoing messages will be set to this value, and
# used by the server message system to lookup the correct MessageAPI adapter
# for handling the messages sent by the client. Bump it when the schema of any
# of the messages sent by the client changes in a backward-incompatible way.
SERVER_API = "3.2"

# The "client-api" field of outgoing messages will be set to this value, and
# used by the server to know which schema do the message types accepted by the
# client support. Bump it when the schema of an accepted message type changes.
CLIENT_API = "3.3"

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
