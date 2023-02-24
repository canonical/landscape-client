from landscape.lib.hashlib import md5


def build_script(interpreter, code):
    """
    Concatenates a interpreter and script into an executable script.
    """
    return "#!{}\n{}".format(interpreter or "", code or "")


def generate_script_hash(script):
    """
    Return a hash for a given script.
    """
    encoded_script = script.encode("utf-8")
    # As this hash is sent in message which requires bytes in the schema, we
    # have to encode here.
    return md5(encoded_script).hexdigest().encode("ascii")
