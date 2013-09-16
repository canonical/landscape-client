DEBIAN_REVISION = ""
UPSTREAM_VERSION = "13.09"
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
#
# 3.5:
#  * Support per-exchange authentication tokens
#
# 3.6:
#  * Handle scopes in resynchronize requests


CLIENT_API = "3.6"
