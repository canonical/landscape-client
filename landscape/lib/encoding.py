from twisted.python.compat import unicode


def encode_if_needed(value):
    """
    A small helper to decode unicode to utf-8 if needed.
    """
    if isinstance(value, unicode):
        value = value.encode("utf-8")
    return value


def encode_values(dictionary):
    """
    Encode values of the given C{dictionary} with utf-8 and surrogateescape.
    """
    _dict = dictionary.copy()
    for key, val in _dict.items():
        if isinstance(val, unicode):
            _dict[key] = val.encode("utf-8", "surrogateescape")
    return _dict
