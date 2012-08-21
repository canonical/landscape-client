import sys

DEBIAN_REVISION = ""
UPSTREAM_VERSION = "12.09"
VERSION = "%s%s" % (UPSTREAM_VERSION, DEBIAN_REVISION)

# The "server-api" field of outgoing messages will be set to this value, and
# used by the server message system to lookup the correct MessageAPI adapter
# for handling the messages sent by the client. Bump it when the schema of any
# of the messages sent by the client changes in a backward-incompatible way.
#
# Changelog:
#
# 3.2:
#  * Add new "eucalyptus-info" and "eucalyptus-info-error" messages.
#
SERVER_API = "3.2"

# XXX This is needed for backward compatibility in the server code importing
# the API variable. We should eventually replace it in the server code.
API = SERVER_API

# The "client-api" field of outgoing messages will be set to this value, and
# used by the server to know which schema do the message types accepted by the
# client support. Bump it when the schema of an accepted message type changes
# and update the changelog below as needed.
#
# Changelog:
#
# 3.3:
#  * Add "binaries" field to "change-packages"
#  * Add "policy" field to "change-packages"
#  * Add new "change-package-locks" client accepted message type.
#
# 3.4:
#  * Add "hold" field to "change-packages"
#  * Add "remove-hold" field to "change-packages"

CLIENT_API = "3.4"

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


if "twisted.python._initgroups" not in sys.modules:
    # Patch twisted initgroups implementation, which can result in very long
    # calls to grp.getrlall(). See http://twistedmatrix.com/trac/ticket/3226
    # We can remove that bit when Lucid is our oldest supported version
    # (May 2013).
    util.initgroups = initgroups
