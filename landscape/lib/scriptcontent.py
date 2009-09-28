from landscape.lib.hashlib import md5

def build_script(interpreter, code):
    """
    Concatenates a interpreter and script into an executable script.
    """
    return "#!%s\n%s" % ((interpreter or u"").encode("utf-8"),
                         (code or u"").encode("utf-8"))


def generate_script_hash(script):
    """
    Return a hash for a given script.
    """
    return md5(script).hexdigest()
