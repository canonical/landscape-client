from __future__ import absolute_import

from landscape.lib.compat import _PY3

if _PY3:
    from base64 import decodebytes  # noqa
else:
    from base64 import decodestring as decodebytes  # noqa
