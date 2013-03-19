

def encode_if_needed(value):
    """
    A small helper to decode unicode to utf-8 if needed.
    """
    if isinstance(value, unicode):
        value = value.encode("utf-8")
    return value


def encode_dict_if_needed(values):
    """
    A wrapper taking a dict and passing each of the values to encode_if_needed.
    """
    for key, value in values.iteritems():
        values[key] = encode_if_needed(value)
    return values
