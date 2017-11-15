from grp import struct_group
from pwd import struct_passwd
import csv
import logging
import subprocess

from twisted.python.compat import _PY3


class UserManagementError(Exception):
    """Catch all error for problems with User Management."""


class UserNotFoundError(Exception):
    """Raised when a user couldn't be found by uid/username."""


class GroupNotFoundError(Exception):
    """Raised when a group couldn't be found by gid/groupname."""


class UserProviderBase(object):
    """This is a base class for user Providers."""

    def __init__(self, locked_users=None):
        self.locked_users = locked_users or []

        self._min_uid = 1000
        self._max_uid = 60000

    def get_users(self):
        """Returns a list of all local users on the computer.

        Each user is represented as a dict with the keys: C{username},
        C{name}, C{uid}, C{enabled}, C{location}, C{work-phone} and
        C{home-phone}.
        """
        users = []
        found_usernames = set()
        for user in self.get_user_data():
            if not isinstance(user, struct_passwd):
                user = struct_passwd(user)
            if user.pw_name in found_usernames:
                continue
            gecos_data = [x or None for x in user.pw_gecos.split(",")[:4]]
            while len(gecos_data) < 4:
                gecos_data.append(None)
            name, location, work_phone, home_phone = tuple(gecos_data)
            enabled = user.pw_name not in self.locked_users
            users.append({"username": user.pw_name, "name": name,
                          "uid": user.pw_uid, "enabled": enabled,
                          "location": location, "work-phone": work_phone,
                          "home-phone": home_phone,
                          "primary-gid": user.pw_gid})
            found_usernames.add(user.pw_name)
        return users

    def get_groups(self):
        """Returns a list of groups on the computer.

        Each group is represented as a dict with the keys: C{name},
        C{gid} and C{members}.
        """
        user_names = set([x["username"] for x in self.get_users()])
        groups = []
        found_groupnames = set()
        for group in self.get_group_data():
            if not isinstance(group, struct_group):
                group = struct_group(group)
            if group.gr_name in found_groupnames:
                continue
            member_names = user_names.intersection(group.gr_mem)
            groups.append({"name": group.gr_name, "gid": group.gr_gid,
                           "members": sorted(list(member_names))})
            found_groupnames.add(group.gr_name)
        return groups

    def get_uid(self, username):
        """Returns the UID for C{username}.

        @raises UserNotFoundError: Raised if C{username} doesn't match a
            user on the computer.
        """
        for data in self.get_users():
            if data["username"] == username:
                return data["uid"]
        raise UserNotFoundError("UID not found for user %s." % username)

    def get_gid(self, groupname):
        """Returns the GID for C{groupname}.

        @raises UserManagementError: Raised if C{groupname} doesn't
            match a group on the computer.
        """
        for data in self.get_groups():
            if data["name"] == groupname:
                return data["gid"]
        raise GroupNotFoundError("Group not found for group %s." % groupname)


class UserProvider(UserProviderBase):

    popen = subprocess.Popen

    passwd_fields = ["username", "passwd", "uid", "primary-gid", "gecos",
                     "home", "shell"]
    group_fields = ["name", "passwd", "gid", "members"]

    def __init__(self, locked_users=[], passwd_file="/etc/passwd",
                 group_file="/etc/group"):
        super(UserProvider, self).__init__(locked_users)
        self._passwd_file = passwd_file
        self._group_file = group_file

    def get_user_data(self):
        """
        Parse passwd(5) formatted files and return tuples of user data in the
        form (username, password, uid, primary-group-id, gecos data, home
        directory, path to the user's shell)
        """
        user_data = []
        # The DictReader takes bytes in Python 2 and unicode in Python 3 so we
        # have to pass Python 3 specific parameters to open() and do the
        # decoding for Python 2 later after we have parsed the rows. We have to
        # explicitly indicate the encoding as we cannot rely on the system
        # default encoding.
        if _PY3:
            open_params = dict(encoding="utf-8", errors='replace')
        else:
            open_params = dict()
        with open(self._passwd_file, "r", **open_params) as passwd_file:
            reader = csv.DictReader(
                passwd_file, fieldnames=self.passwd_fields, delimiter=":",
                quoting=csv.QUOTE_NONE)
            current_line = 0
            for row in reader:
                current_line += 1
                # This skips the NIS user marker in the passwd file.
                if (row["username"].startswith("+") or
                        row["username"].startswith("-")):
                    continue
                gecos = row["gecos"]
                if not _PY3 and gecos is not None:
                    gecos = gecos.decode("utf-8", "replace")
                try:
                    user_data.append((row["username"], row["passwd"],
                                      int(row["uid"]), int(row["primary-gid"]),
                                      gecos, row["home"], row["shell"]))
                except (ValueError, TypeError):
                    logging.warn(
                        "passwd file %s is incorrectly formatted: line %d."
                        % (self._passwd_file, current_line))
        return user_data

    def get_group_data(self):
        """
        Parse group(5) formatted files and return tuples of group data in the
        form (groupname, group password, group id and a list of member
        usernames).
        """
        group_data = []
        group_file = open(self._group_file, "r")
        reader = csv.DictReader(group_file, fieldnames=self.group_fields,
                                delimiter=":", quoting=csv.QUOTE_NONE)
        current_line = 0
        for row in reader:
            current_line += 1
            # Skip if we find the NIS marker
            if (row["name"].startswith("+") or row["name"].startswith("-")):
                continue
            try:
                group_data.append((row["name"], row["passwd"], int(row["gid"]),
                                   row["members"].split(",")))
            except (AttributeError, ValueError):
                logging.warn("group file %s is incorrectly formatted: "
                             "line %d." % (self._group_file, current_line))
        group_file.close()
        return group_data
