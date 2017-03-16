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


dumps_table = {}
loads_table = {}


def dumps(obj, _dt=dumps_table):
    try:
        return _dt[type(obj)](obj)
    except KeyError as e:
        raise ValueError("Unsupported type: %s" % e)


def loads(byte_string, _lt=loads_table):
    if not byte_string:
        raise ValueError("Can't load empty string")
    try:
        # To avoid python3 turning byte_string[0] into an int,
        # we slice the bytestring instead.
        return _lt[byte_string[0:1]](byte_string, 0)[0]
    except KeyError as e:
        raise ValueError("Unknown type character: %s" % e)
    except IndexError:
        raise ValueError("Corrupted data")


def dumps_bool(obj):
    return b"b%d" % int(obj)


def dumps_int(obj):
    return b"i%d;" % obj


def dumps_float(obj):
    return b"f%r;" % obj


def dumps_bytes(obj):
    return b"s%d:%s" % (len(obj), obj)


def dumps_unicode(obj):
    obj = obj.encode("utf-8")
    return b"u%d:%s" % (len(obj), obj)


def dumps_list(obj, _dt=dumps_table):
    return b"l%s;" % b"".join([_dt[type(val)](val) for val in obj])


def dumps_tuple(obj, _dt=dumps_table):
    return b"t%s;" % b"".join([_dt[type(val)](val) for val in obj])


def dumps_dict(obj, _dt=dumps_table):
    keys = list(obj.keys())
    keys.sort()
    res = []
    append = res.append
    for key in keys:
        val = obj[key]
        append(_dt[type(key)](key))
        append(_dt[type(val)](val))
    return b"d%s;" % b"".join(res)


def dumps_none(obj):
    return b"n"


def loads_bool(bytestring, pos):
    return bool(int(bytestring[pos+1:pos+2])), pos+2


def loads_int(bytestring, pos):
    endpos = bytestring.index(b";", pos)
    return int(bytestring[pos+1:endpos]), endpos+1


def loads_float(bytestring, pos):
    endpos = bytestring.index(b";", pos)
    return float(bytestring[pos+1:endpos]), endpos+1


def loads_bytes(bytestring, pos):
    startpos = bytestring.index(b":", pos)+1
    endpos = startpos+int(bytestring[pos+1:startpos-1])
    return bytestring[startpos:endpos], endpos


def loads_unicode(bytestring, pos):
    startpos = bytestring.index(b":", pos)+1
    endpos = startpos+int(bytestring[pos+1:startpos-1])
    return bytestring[startpos:endpos].decode("utf-8"), endpos


def loads_list(bytestring, pos, _lt=loads_table):
    pos += 1
    res = []
    append = res.append
    while bytestring[pos:pos+1] != b";":
        obj, pos = _lt[bytestring[pos:pos+1]](bytestring, pos)
        append(obj)
    return res, pos+1


def loads_tuple(bytestring, pos, _lt=loads_table):
    pos += 1
    res = []
    append = res.append
    while bytestring[pos:pos+1] != b";":
        obj, pos = _lt[bytestring[pos:pos+1]](bytestring, pos)
        append(obj)
    return tuple(res), pos+1


def loads_dict(bytestring, pos, _lt=loads_table):
    pos += 1
    res = {}
    while bytestring[pos:pos+1] != b";":
        key, pos = _lt[bytestring[pos:pos+1]](bytestring, pos)
        val, pos = _lt[bytestring[pos:pos+1]](bytestring, pos)
        res[key] = val
    return res, pos+1


def loads_none(str, pos):
    return None, pos+1


dumps_table.update({
    bool: dumps_bool,
    int: dumps_int,
    float: dumps_float,
    list: dumps_list,
    tuple: dumps_tuple,
    dict: dumps_dict,
    type(None): dumps_none
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


if bytes == str:
    # Python 2.x: We need to map internal strings to bytestrings,
    # and internal unicode strings to UTF-8 encoded strings.
    dumps_table.update({
        str: dumps_bytes,
        unicode: dumps_unicode,
        long: dumps_int,
    })
else:
    # Python 3.x: We need to map internal strings to bytestrings,
    # and internal unicode strings to UTF-8 encoded strings.
    dumps_table.update({
        str: dumps_unicode,
        bytes: dumps_bytes,
    })

