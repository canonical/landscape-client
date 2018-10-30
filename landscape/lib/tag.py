import re


_tag_check = re.compile(r"^\w+[\w-]*$", re.UNICODE)


def is_valid_tag(tagname):
    """Return True if the tag meets our tag requirements."""
    return _tag_check.match(tagname)


def is_valid_tag_list(tag_list):
    """Validate a tag_list string.

    @param tag_list: string like london, server which will be split on the
    commas and each tag verified for validity.
    """
    if not tag_list:
        return True
    return all(is_valid_tag(tag.strip()) for tag in tag_list.split(","))
