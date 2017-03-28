from twisted.python.compat import unicode


def encode_if_needed(value):
    """
    A small helper to decode unicode to utf-8 if needed.
    """
    if isinstance(value, unicode):
        value = value.encode("utf-8")
    return value
