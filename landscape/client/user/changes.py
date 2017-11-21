from twisted.python.compat import iteritems, itervalues

from landscape.client.diff import diff


class UserChanges(object):
    """Detect changes made since the last snapshot was taken.

    If no snapshot is available all users and groups are reported.
    When a snapshot is available, only the changes between the current
    state and the snapshotted state are transmitted to the server.
    """

    def __init__(self, persist, provider):
        super(UserChanges, self).__init__()
        self._persist = persist
        self._provider = provider
        # FIXME This shouldn't really be necessary.  Not having it
        # here with the current factoring is also problematic.  Figure
        # out a clean way to factor this.  Gustavo suggested splitting
        # it into _build_old_data and _build_new_data and just calling
        # that from the necessary places.
        self._refresh()

    def _refresh(self):
        """Load the previous snapshot and update current data."""
        self._old_users = self._persist.get("users", {})
        self._old_groups = self._persist.get("groups", {})
        self._new_users = self._create_index(
            "username", self._provider.get_users())
        self._new_groups = self._create_index(
            "name", self._provider.get_groups())

    def snapshot(self):
        """Save the current state and use it as a comparison snapshot."""
        self._persist.set("users", self._new_users)
        self._persist.set("groups", self._new_groups)

    def clear(self):
        """
        Reset the snapshot state and forget all knowledge of users and
        groups.
        """
        self._persist.remove("users")
        self._persist.remove("groups")

    def _create_index(self, key, sequence):
        """
        Given a key and a sequence of dicts, return a dict of the form
        C{{dict[key]: dict, ...}}.
        """
        index = {}
        for data in sequence:
            index[data[key]] = data
        return index

    def create_diff(self):
        """Returns the changes since the last snapshot.

        See landscape.message_schemas.USERS schema for a description of the
        dictionary returned by this method.
        """
        self._refresh()
        changes = {}
        changes.update(self._detect_user_changes())
        changes.update(self._detect_group_changes())
        return changes

    def _detect_user_changes(self):
        """
        Compare the current user snapshot to the old one and return a
        C{dict} with C{create-users}, C{update-users} and
        C{delete-users} fields.  Fields without data aren't included
        in the result.
        """
        changes = {}
        creates, updates, deletes = diff(self._old_users, self._new_users)
        if creates:
            changes["create-users"] = list(itervalues(creates))
        if updates:
            changes["update-users"] = list(itervalues(updates))
        if deletes:
            changes["delete-users"] = list(deletes)
        return changes

    def _detect_group_changes(self):
        """
        Compare the current group snapshot to the old one and create a
        C{dict} with C{create-groups}, C{delete-groups},
        C{create-group-members} and {delete-group-members} fields.
        Fields without data aren't included in the result.
        """
        changes = {}
        creates, updates, deletes = diff(self._old_groups, self._new_groups)

        if creates:
            groups = []
            create_members = {}
            for value in itervalues(creates):
                # Use a copy to avoid removing the 'members' element
                # from stored data.
                value = value.copy()
                members = value.pop("members")
                if members:
                    create_members[value["name"]] = members
                groups.append(value)
            changes["create-groups"] = groups
            if create_members:
                changes["create-group-members"] = create_members

        if updates:
            remove_members = {}
            create_members = {}
            update_groups = []
            for groupname, new_data in iteritems(updates):
                old_data = self._old_groups[groupname]
                old_members = set(old_data["members"])
                new_members = set(new_data["members"])
                created = new_members - old_members
                if created:
                    create_members[groupname] = sorted(created)
                removed = old_members - new_members
                if removed:
                    remove_members[groupname] = sorted(removed)
                if old_data["gid"] != new_data["gid"]:
                    update_groups.append({"name": groupname,
                                          "gid": new_data["gid"]})
            if create_members:
                members = changes.setdefault("create-group-members", {})
                members.update(create_members)
            if remove_members:
                members = changes.setdefault("delete-group-members", {})
                members.update(remove_members)
            if update_groups:
                members = changes.setdefault("update-groups", [])
                members.extend(update_groups)

        if deletes:
            changes["delete-groups"] = sorted(deletes.keys())

        return changes
