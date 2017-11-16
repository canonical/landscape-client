from landscape.lib.persist import Persist
from landscape.client.user.changes import UserChanges
from landscape.client.user.tests.helpers import FakeUserInfo, FakeUserProvider

from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class UserChangesTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(UserChangesTest, self).setUp()
        self.persist = Persist()
        self.shadow_file = self.makeFile("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")

    def test_no_existing_snapshot(self):
        """
        The diff created by L{UserChanges.create_diff} contains data
        for all users and groups if an existing snapshot isn't
        available.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        self.assertEqual(changes.create_diff(),
                         {"create-users": [{"username": "jdoe",
                                            "home-phone": None,
                                            "name": u"JD",
                                            "enabled": True,
                                            "location": None,
                                            "work-phone": None,
                                            "uid": 1000,
                                            "primary-gid": 1000}],
                          "create-groups": [{"gid": 1000, "name": "webdev"}],
                          "create-group-members": {"webdev": ["jdoe"]}})

    def test_snapshot(self):
        """
        When a snapshot is taken it should persist beyond instance
        invocations and be used as the baseline in
        L{UserChanges.create_diff} until another snapshot is taken.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes1 = UserChanges(self.persist, provider)
        self.assertTrue(changes1.create_diff())
        changes1.snapshot()
        changes2 = UserChanges(self.persist, provider)
        self.assertFalse(changes2.create_diff())

    def test_snapshot_before_diff(self):
        """
        A valid snapshot should be created if L{UserChanges.snapshot}
        is called before L{UserChanges.create_diff}.  When
        L{UserChanges.create_diff} is called it shouln't report any
        changes.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)
        changes = UserChanges(self.persist, provider)
        changes.snapshot()
        self.assertFalse(changes.create_diff())

    def test_clear(self):
        """
        L{UserChanges.clear} removes a snapshot, if present, returning
        the object to a pristine state.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 1000, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        self.assertTrue(changes.create_diff())
        changes.snapshot()
        self.assertFalse(changes.create_diff())
        changes.clear()
        self.assertTrue(changes.create_diff())

    def test_create_diff_without_changes(self):
        """
        L{UserChanges.create_diff} should return an empty C{dict} if
        users and groups are unchanged since the last snapshot.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        provider = FakeUserProvider(users=users)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        self.assertEqual(changes.create_diff(), {})

    def test_add_user(self):
        """
        L{UserChanges.create_diff} should report new users created
        externally with C{adduser} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        provider = FakeUserProvider(users=users)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        users.append(("bo", "x", 1001, 1001, "Bo,,,,", "/home/bo", "/bin/sh"))
        self.assertEqual(changes.create_diff(),
                         {"create-users": [{"username": "bo",
                                            "home-phone": None,
                                            "name": u"Bo",
                                            "enabled": True,
                                            "location": None,
                                            "work-phone": None,
                                            "uid": 1001,
                                            "primary-gid": 1001}]})

    def test_update_user(self):
        """
        L{UserChanges.create_diff} should report users modified
        externally with C{usermod} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        provider = FakeUserProvider(users=users)
        FakeUserInfo(provider=provider)
        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        users[0] = ("jdoe", "x", 1000, 1001, "John Doe,Here,789WORK,321HOME",
                    "/home/john", "/bin/zsh")
        self.assertEqual(changes.create_diff(),
                         {"update-users": [{"username": "jdoe",
                                            "home-phone": u"321HOME",
                                            "name": u"John Doe",
                                            "enabled": True,
                                            "location": "Here",
                                            "work-phone": "789WORK",
                                            "uid": 1000,
                                            "primary-gid": 1001}]})

    def test_delete_user(self):
        """
        L{UserChanges.create_diff} should report users removed
        externally with C{deluser} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh"),
                 ("bo", "x", 1001, 1001, "Bo,,,,", "/home/bo", "/bin/sh")]
        provider = FakeUserProvider(users=users)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        users.pop()
        self.assertEqual(changes.create_diff(), {"delete-users": ["bo"]})

    def test_add_group(self):
        """
        L{UserChanges.create_diff} should report new groups created
        externally with C{addgroup} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups.append(("bizdev", "x", 60, []))
        self.assertEqual(changes.create_diff(),
                         {"create-groups": [{"gid": 60, "name": "bizdev"}]})

    def test_add_group_with_members(self):
        """
        L{UserChanges.create_diff} should report new groups and new
        members created externally with C{addgroup} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups.append(("bizdev", "x", 60, ["jdoe"]))
        self.assertEqual(changes.create_diff(),
                         {"create-groups": [{"gid": 60, "name": "bizdev"}],
                          "create-group-members": {"bizdev": ["jdoe"]}})

    def test_update_group(self):
        """
        L{UserChanges.create_diff} should report groups modified
        externally with C{groupmod} or similar tools.
        """
        groups = [("webdev", "x", 1000, [])]
        provider = FakeUserProvider(groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups[0] = ("webdev", "x", 1001, [])
        self.assertEqual(changes.create_diff(),
                         {"update-groups": [{"gid": 1001, "name": "webdev"}]})

    def test_add_group_members(self):
        """
        L{UserChanges.create_diff} should report new members added to
        groups externally with C{gpasswd} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh"),
                 ("bo", "x", 1001, 1001, "Bo,,,,", "/home/bo", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups[0] = ("webdev", "x", 50, ["jdoe", "bo"])
        self.assertEqual(changes.create_diff(),
                         {"create-group-members": {"webdev": ["bo"]}})

    def test_delete_group_members(self):
        """
        L{UserChanges.create_diff} should report members removed from
        groups externally with C{gpasswd} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups[0] = ("webdev", "x", 50, [])
        self.assertEqual(changes.create_diff(),
                         {"delete-group-members": {"webdev": ["jdoe"]}})

    def test_delete_group(self):
        """
        L{UserChanges.create_diff} should report groups removed
        externally with C{delgroup} or similar tools.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"]), ("sales", "x", 60, [])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)

        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        groups.pop()
        self.assertEqual(changes.create_diff(), {"delete-groups": ["sales"]})

    def test_complex_changes(self):
        """
        L{UserChanges.create_diff} should be able to report multiple
        kinds of changes at the same time.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/sh"),
                 ("bo", "x", 1001, 1001, "Bo,,,,", "/home/bo", "/bin/sh")]
        groups = [("webdev", "x", 50, ["jdoe"]),
                  ("bizdev", "x", 60, ["bo"])]
        provider = FakeUserProvider(users=users, groups=groups)
        FakeUserInfo(provider=provider)
        changes = UserChanges(self.persist, provider)
        changes.create_diff()
        changes.snapshot()
        # We remove the group "webdev", and create a new group
        # "developers", adding the user "bo" at the same time.
        groups[0] = ("developers", "x", 50, ["bo"])
        # Add a new group "sales" and a new group member, "bo"
        groups.append(("sales", "x", 70, ["bo"]))
        # Remove user "jdoe"
        users.pop(0)

        self.assertCountEqual(
            changes.create_diff(),
            {"create-groups": [{"gid": 50, "name": "developers"},
                               {"gid": 70, "name": "sales"}],
             "delete-users": ["jdoe"],
             "delete-groups": ["webdev"],
             "create-group-members": {"developers": ["bo"],
                                      "sales": ["bo"]}})
