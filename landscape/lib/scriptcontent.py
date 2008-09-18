import md5

def concatenate_script(interpreter, code):
    """
    Concatenates a interpreter and script into an executable script.
    """
    return "#!%s\n%s" % (interpreter.encode("utf-8"), code.encode("utf-8"))

def generate_script_hash(script):
    """
    Return a hash for a given script.
    """
    return md5.new(script).hexdigest()
