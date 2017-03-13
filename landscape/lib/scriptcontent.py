from landscape.lib.hashlib import md5


def build_script(interpreter, code):
    """
    Concatenates a interpreter and script into an executable script.
    """
    return u"#!{}\n{}".format(interpreter or u"", code or u"")


def generate_script_hash(script):
    """
    Return a hash for a given script.
    """
    encoded_script = script.encode('utf-8')
    return md5(encoded_script).hexdigest()
