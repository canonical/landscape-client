"""
Copyright (c) 2006, Gustavo Niemeyer <gustavo@niemeyer.net>
Port to python 3 was done by Chris Glass <chris.glass@canonical.com>

All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    * Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    * Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    * Neither the name of the copyright holder nor the names of its
      contributors may be used to endorse or promote products derived from
      this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

This file is modified from the original to work with python3, but should be
wire compatible and behave the same way (bugs notwithstanding).
"""

from twisted.python.compat import _PY3

dumps_table = {}
loads_table = {}


def dumps(obj, _dt=dumps_table):
    try:
        return _dt[type(obj)](obj)
    except KeyError as e:
        raise ValueError("Unsupported type: %s" % e)


def loads(byte_string, _lt=loads_table, as_is=False):
    """Load a serialized byte_string.

    @param byte_string: the serialized data
    @param _lt: the conversion map
    @param as_is: don't reinterpret dict keys as str
    """
    if not byte_string:
        raise ValueError("Can't load empty string")
    try:
        # To avoid python3 turning byte_string[0] into an int,
        # we slice the bytestring instead.
        return _lt[byte_string[0:1]](byte_string, 0, as_is=as_is)[0]
    except KeyError as e:
        raise ValueError("Unknown type character: %s" % e)
    except IndexError:
        raise ValueError("Corrupted data")


def dumps_bool(obj):
    return ("b%d" % int(obj)
            ).encode("utf-8")


def dumps_int(obj):
    return ("i%d;" % obj
            ).encode("utf-8")


def dumps_float(obj):
    return ("f%r;" % obj
            ).encode("utf-8")


def dumps_bytes(obj):
    return ("s%d:" % (len(obj),)).encode("utf-8") + obj


def dumps_unicode(obj):
    bobj = obj.encode("utf-8")
    return ("u%d:%s" % (len(bobj), obj)
            ).encode("utf-8")


def dumps_list(obj, _dt=dumps_table):
    return b"l" + b"".join([_dt[type(val)](val) for val in obj]) + b";"


def dumps_tuple(obj, _dt=dumps_table):
    return b"t" + b"".join([_dt[type(val)](val) for val in obj]) + b";"


def dumps_dict(obj, _dt=dumps_table):
    keys = list(obj.keys())
    keys.sort()
    res = []
    append = res.append
    for key in keys:
        val = obj[key]
        append(_dt[type(key)](key))
        append(_dt[type(val)](val))
    return b"d" + b"".join(res) + b";"


def dumps_none(obj):
    return b"n"


def loads_bool(bytestring, pos, as_is=False):
    return bool(int(bytestring[pos+1:pos+2])), pos+2


def loads_int(bytestring, pos, as_is=False):
    endpos = bytestring.index(b";", pos)
    return int(bytestring[pos+1:endpos]), endpos+1


def loads_float(bytestring, pos, as_is=False):
    endpos = bytestring.index(b";", pos)
    return float(bytestring[pos+1:endpos]), endpos+1


def loads_bytes(bytestring, pos, as_is=False):
    startpos = bytestring.index(b":", pos)+1
    endpos = startpos+int(bytestring[pos+1:startpos-1])
    return bytestring[startpos:endpos], endpos


def loads_unicode(bytestring, pos, as_is=False):
    startpos = bytestring.index(b":", pos)+1
    endpos = startpos+int(bytestring[pos+1:startpos-1])
    return bytestring[startpos:endpos].decode("utf-8"), endpos


def loads_list(bytestring, pos, _lt=loads_table, as_is=False):
    pos += 1
    res = []
    append = res.append
    while bytestring[pos:pos+1] != b";":
        obj, pos = _lt[bytestring[pos:pos+1]](bytestring, pos, as_is=as_is)
        append(obj)
    return res, pos+1


def loads_tuple(bytestring, pos, _lt=loads_table, as_is=False):
    pos += 1
    res = []
    append = res.append
    while bytestring[pos:pos+1] != b";":
        obj, pos = _lt[bytestring[pos:pos+1]](bytestring, pos, as_is=as_is)
        append(obj)
    return tuple(res), pos+1


def loads_dict(bytestring, pos, _lt=loads_table, as_is=False):
    pos += 1
    res = {}
    while bytestring[pos:pos+1] != b";":
        key, pos = _lt[bytestring[pos:pos+1]](bytestring, pos, as_is=as_is)
        val, pos = _lt[bytestring[pos:pos+1]](bytestring, pos, as_is=as_is)
        if _PY3 and not as_is and isinstance(key, bytes):
            # Although the wire format of dictionary keys is ASCII bytes, the
            # code actually expects them to be strings, so we convert them
            # here.
            key = key.decode("ascii")
        res[key] = val
    return res, pos+1


def loads_none(str, pos, as_is=False):
    return None, pos+1


dumps_table.update({
    bool: dumps_bool,
    int: dumps_int,
    float: dumps_float,
    list: dumps_list,
    tuple: dumps_tuple,
    dict: dumps_dict,
    type(None): dumps_none,
    bytes: dumps_bytes,
})


loads_table.update({
    b"b": loads_bool,
    b"i": loads_int,
    b"f": loads_float,
    b"l": loads_list,
    b"t": loads_tuple,
    b"d": loads_dict,
    b"n": loads_none,
    b"s": loads_bytes,
    b"u": loads_unicode,
})


if bytes is str:
    # Python 2.x: We need to map internal unicode strings to UTF-8
    # encoded strings, and longs to ints.
    dumps_table.update({
        unicode: dumps_unicode,  # noqa
        long: dumps_int,  # noqa
        })
else:
    # Python 3.x: We need to map internal strings to UTF-8 encoded strings.
    dumps_table.update({
        str: dumps_unicode,
        })
