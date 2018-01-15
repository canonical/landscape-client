DEBIAN_REVISION = ""
UPSTREAM_VERSION = "18.01"
VERSION = "%s%s" % (UPSTREAM_VERSION, DEBIAN_REVISION)

# The minimum server API version that all Landscape servers are known to speak
# and support. It can serve as fallback in case higher versions are not there.
DEFAULT_SERVER_API = b"3.2"

# The highest server API version that the client is capable of speaking. The
# client will use it, unless the server declares to support only a lower
# version. In that case the server's version will be used. The client will set
# the X-Message-API HTTP header and the "server-api" payload field of outgoing
# requests to this value, and the server message system will use it to lookup
# the correct MessageAPI adapter for handling the messages sent by the client.
# Bump it when the schema of any of the messages sent by the client changes in
# a backward-incompatible way.
#
# Changelog:
#
# 3.2:
#  * Add new "eucalyptus-info" and "eucalyptus-info-error" messages.
# 3.3:
#  * Add new schema for the "registration" message, providing Juju information
#
SERVER_API = b"3.3"

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
#
# 3.7:
#  * Server returns 402 Payment Required if the computer has no valid license.
#
# 3.8:
#  * Handle the new "max-pending-computers" key returned by the server in the
#    "info" field of the response payload for a fail registration, in case the
#    account has too many pending computers.
#
CLIENT_API = b"3.8"
