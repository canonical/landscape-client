def diff(old, new):
    """Returns the set of differences between two C{dict}s.

    @return: A 3-tuple of dicts with the changes that would need to be
        made to convert C{old} into C{new}: C{(creates, updates, deletes)}
    """
    new_keys = set(new)
    old_keys = set(old)

    creates = {}
    for key in new_keys - old_keys:
        creates[key] = new[key]

    updates = {}
    for key in old_keys & new_keys:
        if old[key] != new[key]:
            updates[key] = new[key]

    deletes = {}
    for key in old_keys - new_keys:
        deletes[key] = old[key]

    return creates, updates, deletes
