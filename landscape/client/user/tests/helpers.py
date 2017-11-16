from twisted.python.compat import iteritems, itervalues

from landscape.client.user.management import UserManagementError
from landscape.client.user.provider import UserProviderBase


class FakeUserManagement(object):

    def __init__(self, provider=None):
        self.shadow_file = getattr(provider, "shadow_file", None)
        self.provider = provider
        self._users = {}

        for data in self.provider.get_users():
            self._users[data["username"]] = data
        self._groups = {}
        for data in self.provider.get_groups():
            self._groups[data["name"]] = data

    def _make_fake_shadow_file(self, locked_users, unlocked_users):
        entry = "%s:%s:13348:0:99999:7:::\n"
        shadow_file = open(self.shadow_file, "w")
        for user in locked_users:
            shadow_file.write(entry % (user, "!"))
        for user in unlocked_users:
            shadow_file.write(entry % (user, "qweqweqeqweqw"))
        shadow_file.close()

    def add_user(self, username, name, password, require_password_reset,
                 primary_group_name, location, work_phone, home_phone):
        try:
            uid = 1000
            if self._users:
                uid = max([x["uid"] for x in itervalues(self._users)]) + 1
            if self._groups:
                primary_gid = self.get_gid(primary_group_name)
            else:
                primary_gid = uid
            self._users[uid] = {"username": username, "name": name,
                                "uid": uid, "enabled": True,
                                "location": location, "work-phone": work_phone,
                                "home-phone": home_phone,
                                "primary-gid": primary_gid}
            gecos_string = "%s,%s,%s,%s" % (name, location or "",
                                            work_phone or "", home_phone or "")
            userdata = (username, "x", uid, primary_gid, gecos_string,
                        "/bin/sh", "/home/user")
            self.provider.users.append(userdata)
        except KeyError:
            raise UserManagementError("add_user failed")
        return "add_user succeeded"

    def lock_user(self, username):
        data = self._users.get(username, None)
        if data:
            data["enabled"] = False
            # This will generate a shadow file with only the locked user in it.
            self._make_fake_shadow_file([username], [])
            return "lock_user succeeded"
        raise UserManagementError("lock_user failed")

    def unlock_user(self, username):
        data = self._users.get(username, None)
        if data:
            data["enabled"] = True
            # This will generate a shadow file with only the unlocked user in
            # it.
            self._make_fake_shadow_file([], [username])
            return "unlock_user succeeded"
        raise UserManagementError("unlock_user failed")

    def remove_user(self, username, delete_home=False):
        try:
            del self._users[username]
        except KeyError:
            raise UserManagementError("remove_user failed")
        remaining_users = []
        for user in self.provider.users:
            if user[0] != username:
                remaining_users.append(user)
        self.provider.users = remaining_users
        return "remove_user succeeded"

    def set_user_details(self, username, password=None, name=None,
                         location=None, work_number=None, home_number=None,
                         primary_group_name=None):
        data = self._users.setdefault(username, {})
        for key, value in [("name", name),
                           ("location", location),
                           ("work-phone", work_number),
                           ("home-phone", home_number),
                           ]:
            if value:
                data[key] = value
        if primary_group_name:
            data["primary-gid"] = self.get_gid(primary_group_name)
        else:
            data["primary-gid"] = None
        userdata = (username, "x", data["uid"], data["primary-gid"],
                    "%s,%s,%s,%s," % (name, location, work_number,
                                      home_number),
                    "/bin/sh", "/home/user")
        self.provider.users = [userdata]
        return "set_user_details succeeded"

    def get_gid(self, name):
        try:
            return self._groups[name]["gid"]
        except KeyError:
            raise UserManagementError("Group %s wasn't found." % name)

    def add_group(self, name):
        gid = 1000
        if self._groups:
            gid = max([x["gid"] for x in itervalues(self._groups)]) + 1
        self._groups[name] = {"name": name, "gid": gid, "members": []}
        self.update_provider_from_groups()
        return "add_group succeeded"

    def set_group_details(self, group, new_name):
        data = self._groups[group]
        data["name"] = new_name
        self._groups[new_name] = data
        del self._groups[group]
        self.update_provider_from_groups()
        return "set_group_details succeeded"

    def add_group_member(self, username, group):
        data = self._groups[group]
        if data:
            data["members"].append(username)
            self.update_provider_from_groups()
            return "add_group_member succeeded"
        raise UserManagementError("add_group_member failed")

    def remove_group_member(self, username, group):
        if group in self._groups:
            data = self._groups[group]
            data["members"].remove(username)
            self.update_provider_from_groups()
            return "remove_group_member succeeded"
        raise UserManagementError("remove_group_member failed")

    def remove_group(self, group):
        del self._groups[group]
        self.update_provider_from_groups()
        return "remove_group succeeded"

    def update_provider_from_groups(self):
        provider_list = []
        for k, v in iteritems(self._groups):
            provider_list.append((k, "x", v["gid"], v["members"]))
        self.provider.groups = provider_list


class FakeUserProvider(UserProviderBase):

    def __init__(self, users=None, groups=None, popen=None, shadow_file=None,
                 locked_users=None):
        self.users = users
        self.groups = groups
        if popen:
            self.popen = popen
        self.shadow_file = shadow_file
        super(FakeUserProvider, self).__init__(locked_users=locked_users)

    def get_user_data(self, system=False):
        if self.users is None:
            self.users = []
        return self.users

    def get_group_data(self):
        if self.groups is None:
            self.groups = []
        return self.groups


class FakeUserInfo(object):
    """Implements enough functionality to work for Changes tests."""

    persist_name = "users"
    run_interval = 60

    def __init__(self, provider):
        self._provider = provider

    def register(self, manager):
        self._manager = manager
        self._persist = self._manager.persist.root_at("users")
