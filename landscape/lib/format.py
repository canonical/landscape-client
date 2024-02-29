import inspect
import re


def format_object(object):
    """
    Returns a fully-qualified name for the specified object, such as
    'landscape.lib.format.format_object()'.
    """
    if inspect.ismethod(object):
        # FIXME If the method is implemented on a base class of
        # object's class, the module name and function name will be
        # from the base class and the method's class name will be from
        # object's class.
        name = repr(object).split(" ")[2]
        return f"{object.__module__}.{name}()"
    elif inspect.isfunction(object):
        name = repr(object).split(" ")[1]
        return f"{object.__module__}.{name}()"
    return f"{object.__class__.__module__}.{object.__class__.__name__}"


def format_delta(seconds):
    if not seconds:
        seconds = 0.0
    return f"{float(seconds):.02f}s"


def format_percent(percent):
    if not percent:
        percent = 0.0
    return f"{float(percent):.02f}%"


def expandvars(pattern: str, **kwargs) -> str:
    """Expand the pattern by replacing the params with values in `kwargs`.

    This implements a small subset of shell parameter expansion and the
    patterns can only be in the following forms:
        - ${parameter}
        - ${parameter:offset} - start at `offset` to the end
        - ${parameter:offset:length} - start at `offset` to `offset + length`
    For simplicity, `offset` and `length` MUST be positive values.
    """
    regex = re.compile(
        r"\$\{([a-zA-Z][a-zA-Z0-9]*)(?::([0-9]+))?(?::([0-9]+))?\}",
        re.MULTILINE,
    )
    values = {k: str(v) for k, v in kwargs.items()}

    def _replace(match):
        param = match.group(1)
        result = values[param.lower()]

        offset, length = match.group(2), match.group(3)
        if offset:
            start = int(offset)
            end = None
            if length:
                end = start + int(length)
            return result[start:end]

        return result

    return re.sub(regex, _replace, pattern)
