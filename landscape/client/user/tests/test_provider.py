import pwd
import grp

from landscape.client.user.provider import (
    UserProvider, UserNotFoundError, GroupNotFoundError)

from landscape.client.tests.helpers import LandscapeTest
from landscape.client.user.tests.helpers import FakeUserProvider


class ProviderTest(LandscapeTest):

    def setUp(self):
        LandscapeTest.setUp(self)
        self.shadow_file = self.makeFile("""\
jdoe:$1$xFlQvTqe$cBtrNEDOIKMy/BuJoUdeG0:13348:0:99999:7:::
psmith:!:13348:0:99999:7:::
sbarnes:$1$q7sz09uw$q.A3526M/SHu8vUb.Jo1A/:13349:0:99999:7:::
""")

        self.passwd_file = self.makeFile("""\
root:x:0:0:root:/root:/bin/bash
haldaemon:x:107:116:Hardware abstraction layer,,,:/home/haldaemon:/bin/false
kevin:x:1001:65534:Kevin,101,+44123123,+44123124:/home/kevin:/bin/bash
""")

        self.group_file = self.makeFile("""\
root:x:0:
cdrom:x:24:haldaemon,kevin
kevin:x:1000:
""")

    def test_get_uid(self):
        """
        Given a username L{UserProvider.get_uid} returns the UID or
        raises a L{UserProviderError} if a match isn't found.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        self.assertEqual(provider.get_uid("jdoe"), 1000)
        self.assertRaises(UserNotFoundError, provider.get_uid, "john")

    def test_get_users(self):
        """Get users should return data for all users found on the system."""
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": None, "home-phone": None,
                                  "work-phone": None,
                                  "primary-gid": 1000}])

    def test_gecos_data(self):
        """
        Location, home phone number, and work phone number should be
        correctly parsed out of the GECOS field, and included in the
        users message.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,Everywhere,7654321,123HOME,",
                 "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": u"Everywhere",
                                  "home-phone": u"123HOME",
                                  "work-phone": u"7654321",
                                  "primary-gid": 1000}])

    def test_four_gecos_fields(self):
        """If a GECOS field only has four fields it should still work."""
        data = [("jdoe", "x", 1000, 1000, "JD,Everywhere,7654321,123HOME",
                 "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": u"Everywhere",
                                  "home-phone": u"123HOME",
                                  "work-phone": u"7654321",
                                  "primary-gid": 1000}])

    def test_old_school_gecos_data(self):
        """
        If C{useradd} is used to add users to a system the GECOS field
        will be written as a comment.  The client must be resilient to
        this situation.
        """
        data = [("jdoe", "x", 1000, 1000, "John Doe",
                 "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "uid": 1000,
                                  "enabled": True, "name": u"John Doe",
                                  "location": None, "home-phone": None,
                                  "work-phone": None, "primary-gid": 1000}])

    def test_weird_gecos_data(self):
        """
        If GECOS data is malformed in a way that contains less than
        four fields, read as many as are available.
        """
        data = [("jdoe", "x", 1000, 1000, "John Doe,Everywhere",
                 "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "uid": 1000,
                                  "enabled": True, "name": "John Doe",
                                  "location": "Everywhere",
                                  "home-phone": None, "work-phone": None,
                                  "primary-gid": 1000}])

    def test_no_gecos_data(self):
        """
        When no data is provided in the GECOS field we should report
        all optional fields as C{None}.
        """
        data = [("jdoe", "x", 1000, 1000, "", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "uid": 1000,
                                  "enabled": True, "name": None,
                                  "location": None, "home-phone": None,
                                  "work-phone": None,
                                  "primary-gid": 1000}])

    def test_utf8_gecos_data(self):
        """Gecos fields should be decoded from utf-8 to unicode."""
        name = u"Jos\N{LATIN SMALL LETTER E WITH ACUTE}"
        location = u"F\N{LATIN SMALL LETTER I WITH DIAERESIS}nland"
        number = u"N\N{LATIN SMALL LETTER AE}ver"
        gecos = u"{},{},{},{},".format(name, location, number, number)
        # We explicitly want to encode this file with utf-8 so we can write in
        # binary mode and do not rely on the default encoding.
        utf8_content = u"""\
jdoe:x:1000:1000:{}:/home/jdoe:/bin/zsh
root:x:0:0:root:/root:/bin/bash
""".format(gecos).encode("utf-8")
        passwd_file = self.makeFile(utf8_content, mode="wb")
        provider = UserProvider(passwd_file=passwd_file,
                                group_file=self.group_file)
        users = provider.get_users()
        self.assertEqual(users[0]["name"], name)
        self.assertEqual(users[0]["location"], location)
        self.assertEqual(users[0]["home-phone"], number)
        self.assertEqual(users[0]["work-phone"], number)

    def test_non_utf8_data(self):
        """
        If a GECOS field contains non-UTF8 data, it should be replaced
        with question marks.
        """
        passwd_file = self.makeFile(b"""\
jdoe:x:1000:1000:\255,\255,\255,\255:/home/jdoe:/bin/zsh
root:x:0:0:root:/root:/bin/bash
""", mode="wb")
        provider = UserProvider(passwd_file=passwd_file,
                                group_file=self.group_file)
        unicode_unknown = u'\N{REPLACEMENT CHARACTER}'
        provider = UserProvider(passwd_file=passwd_file, group_file=None)
        users = provider.get_users()
        self.assertEqual(users[0]["name"], unicode_unknown)
        self.assertEqual(users[0]["location"], unicode_unknown)
        self.assertEqual(users[0]["home-phone"], unicode_unknown)
        self.assertEqual(users[0]["work-phone"], unicode_unknown)

    def test_get_disabled_user(self):
        """The C{enabled} field should be C{False} for disabled users."""
        data = [("psmith", "x", 1000, 1000,
                 "Peter Smith,,,,", "/home/psmith", "/bin/bash")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file,
                                    locked_users=["psmith"])
        users = provider.get_users()
        self.assertEqual(users, [
                {"username": "psmith", "name": u"Peter Smith", "uid": 1000,
                 "enabled": False,
                 "location": None, "home-phone": None, "work-phone": None,
                 "primary-gid": 1000}])

    def test_real_user_data(self):
        """L{UserProvider} should work with real data."""
        provider = UserProvider()
        provider.shadow_file = None
        users = provider.get_users()
        user_0 = pwd.getpwuid(0)
        for user in users:
            if user["username"] == user_0.pw_name:
                self.assertEqual(user["uid"], 0)
                user_0_name = user_0.pw_gecos.split(",")[0]
                self.assertEqual(user["name"], user_0_name)
                break
        else:
            self.fail("The user %s (uid=0) was not found in the get_data "
                      "result." % (user_0.pw_name))

    def test_get_users_duplicate_usernames(self):
        """
        Get users should return data for all users found on the system, but it
        should exclude duplicate usernames.
        """
        data = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh"),
                ("jdoe", "x", 1001, 1001, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "jdoe", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": None, "home-phone": None,
                                  "work-phone": None, "primary-gid": 1000}])

    def test_get_users_duplicate_uids(self):
        """
        Get users should return data for all users found on the system,
        including users with duplicated uids.
        """
        data = [("joe1", "x", 1000, 1000, "JD,,,,", "/home/joe1", "/bin/zsh"),
                ("joe2", "x", 1000, 1000, "JD,,,,", "/home/joe2", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(users, [{"username": "joe1", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": None, "home-phone": None,
                                  "work-phone": None, "primary-gid": 1000},
                                 {"username": "joe2", "name": u"JD",
                                  "uid": 1000, "enabled": True,
                                  "location": None, "home-phone": None,
                                  "work-phone": None, "primary-gid": 1000}])

    def test_user_not_in_shadow_file(self):
        """
        Given a username that doesn't exist in the shadow file, we should get a
        UserProvider error rather than a KeyError.
        raises a L{UserProviderError} if a match isn't found.
        """
        data = [("johndoe", "x", 1000, 1000,
                 "JD,,,,", "/home/jdoe", "/bin/zsh")]
        provider = FakeUserProvider(users=data, shadow_file=self.shadow_file)
        users = provider.get_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(sorted([x[0] for x in data]), ["johndoe"])

    def test_get_gid(self):
        """
        Given a username L{UserProvider.get_gid} returns the GID or
        raises a L{UserProviderError} if a match isn't found.
        """
        provider = FakeUserProvider(groups=[("jdoe", "x", 1000, [])])
        self.assertEqual(provider.get_gid("jdoe"), 1000)
        self.assertRaises(GroupNotFoundError, provider.get_gid, "john")

    def test_group_without_members(self):
        """
        L{UserProvider.get_groups} should include groups without
        members.
        """
        provider = FakeUserProvider(groups=[("jdoe", "x", 1000, [])])
        self.assertEqual(provider.get_groups(),
                         [{"name": "jdoe", "gid": 1000, "members": []}])

    def test_group_with_members(self):
        """L{UserProvider.get_groups} should include groups with members."""
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("sales", "x", 50, ["jdoe"])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups)
        self.assertEqual(provider.get_groups(),
                         [{"name": "sales", "gid": 50, "members": ["jdoe"]}])

    def test_group_with_unknown_members(self):
        """L{UserProvider.get_groups} should include groups with members.

        If a member's userid isn't known to the system, it shouldn't be
        returned.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("sales", "x", 50, ["jdoe", "kevin"])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups)
        self.assertEqual(provider.get_groups(),
                         [{"name": "sales", "gid": 50, "members": ["jdoe"]}])

    def test_group_with_duplicate_members(self):
        """
        L{UserProvider.get_groups} should only report groups once.
        If duplicates exist they should be removed.  The problem
        reported in bug #118799 is related to duplicates being
        reported to the server.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("sales", "x", 50, ["jdoe", "jdoe"])]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups)
        self.assertEqual(provider.get_groups(),
                         [{"name": "sales", "gid": 50, "members": ["jdoe"]}])

    def test_group_with_duplicate_groupnames(self):
        """
        L{UserProvider.get_groups} should only report members once.
        If duplicates exist they should be removed.  The problem
        reported in bug #118799 is related to duplicates being
        reported to the server.
        """
        users = [("jdoe", "x", 1000, 1000, "JD,,,,", "/home/jdoe", "/bin/zsh")]
        groups = [("sales", "x", 50, ["jdoe"]),
                  ("sales", "x", 51, ["jdoe"]),
                  ]
        provider = FakeUserProvider(users=users, shadow_file=self.shadow_file,
                                    groups=groups)
        self.assertEqual(provider.get_groups(),
                         [{"name": "sales", "gid": 50, "members": ["jdoe"]}])

    def test_real_group_data(self):
        """
        Assert that L{UserProvider.get_group}'s functionality
        reflects what is accessible from the Python standard C{grp}
        module.
        """
        provider = UserProvider()
        group_0 = grp.getgrgid(0)
        groups = provider.get_groups()
        for group in groups:
            if group["name"] == group_0.gr_name:
                self.assertEqual(group["gid"], 0)
                self.assertEqual(group["members"], group_0.gr_mem)
                break
        else:
            self.fail("The group %s (gid=0) was not found in the get_data "
                      "result." % (group_0.gr_name,))

    def test_get_user_data(self):
        """This tests the functionality for parsing /etc/passwd style files."""
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=self.group_file)
        users = provider.get_user_data()
        self.assertEqual(users[0], ("root", "x", 0, 0, "root", "/root",
                                    "/bin/bash"))
        self.assertEqual(users[1], ("haldaemon", "x", 107, 116,
                                    "Hardware abstraction layer,,,",
                                    "/home/haldaemon", "/bin/false"))
        self.assertEqual(users[2], ("kevin", "x", 1001, 65534,
                                    "Kevin,101,+44123123,+44123124",
                                    "/home/kevin", "/bin/bash"))

    def test_get_users_with_many(self):
        """
        The method get_users is responsible for translating tuples of
        information from the underlying user database into dictionaries.
        """
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=self.group_file)
        users = provider.get_users()
        self.assertEqual(users[0], {"username": "root",
                                    "name": u"root",
                                    "uid": 0, "enabled": True,
                                    "location": None,
                                    "home-phone": None,
                                    "work-phone": None,
                                    "primary-gid": 0})
        self.assertEqual(users[1], {"username": "haldaemon",
                                    "name": u"Hardware abstraction layer",
                                    "uid": 107,
                                    "enabled": True,
                                    "location": None,
                                    "home-phone": None,
                                    "work-phone": None,
                                    "primary-gid": 116})
        self.assertEqual(users[2], {"username": "kevin",
                                    "name": u"Kevin",
                                    "uid": 1001,
                                    "enabled": True,
                                    "location": u"101",
                                    "home-phone": u"+44123124",
                                    "work-phone": u"+44123123",
                                    "primary-gid": 65534})

    def test_get_group_data(self):
        """This tests the functionality for parsing /etc/group style files."""
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=self.group_file)
        groups = provider.get_group_data()
        self.assertEqual(groups[0], (u"root", u"x", 0, [u""]))
        self.assertEqual(groups[1], (u"cdrom", u"x", 24,
                                     [u"haldaemon", u"kevin"]))
        self.assertEqual(groups[2], (u"kevin", u"x", 1000, [u""]))

    def test_get_groups(self):
        """
        The method get_groups is responsible for translating tuples of data
        from the underlying userdatabase into dictionaries.
        """
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=self.group_file)
        groups = provider.get_groups()
        self.assertEqual(groups[0], {"name": u"root",
                                     "gid": 0,
                                     "members": []})
        self.assertEqual(groups[1], {"name": u"cdrom",
                                     "gid": 24,
                                     "members": [u"haldaemon", u"kevin"]})
        self.assertEqual(groups[2], {"name": u"kevin",
                                     "gid": 1000,
                                     "members": []})

    def test_get_users_incorrect_passwd_file(self):
        """
        This tests the functionality for parsing /etc/passwd style files.

        Incorrectly formatted lines according to passwd(5) should be ignored
        during processing.
        """
        passwd_file = self.makeFile("""\
root:x:0:0:root:/root:/bin/bash
broken
haldaemon:x:107:Hardware abstraction layer,,,:/home/haldaemon:/bin/false
kevin:x:1001:65534:Kevin,101,+44123123,+44123124:/home/kevin:/bin/bash
+::::::
broken2
""")

        provider = UserProvider(passwd_file=passwd_file,
                                group_file=self.group_file)
        users = provider.get_users()
        self.assertEqual(users[0], {"username": "root",
                                    "name": u"root",
                                    "uid": 0, "enabled": True,
                                    "location": None,
                                    "home-phone": None,
                                    "work-phone": None,
                                    "primary-gid": 0})
        self.assertEqual(users[1], {"username": "kevin",
                                    "name": u"Kevin",
                                    "uid": 1001,
                                    "enabled": True,
                                    "location": u"101",
                                    "home-phone": u"+44123124",
                                    "work-phone": u"+44123123",
                                    "primary-gid": 65534})
        log1 = ("WARNING: passwd file %s is incorrectly formatted: line 2." %
                passwd_file)
        self.assertIn(log1, self.logfile.getvalue())
        log2 = ("WARNING: passwd file %s is incorrectly formatted: line 3." %
                passwd_file)
        self.assertIn(log2, self.logfile.getvalue())
        log3 = ("WARNING: passwd file %s is incorrectly formatted: line 6." %
                passwd_file)
        self.assertIn(log3, self.logfile.getvalue())

    def test_get_users_nis_line(self):
        """
        This tests the functionality for parsing /etc/passwd style files.

        We should ignore the specific pattern for NIS user-extensions in passwd
        files.
        """
        passwd_file = self.makeFile("""\
root:x:0:0:root:/root:/bin/bash
kevin:x:1001:65534:Kevin,101,+44123123,+44123124:/home/kevin:/bin/bash
+jkakar::::::
-radix::::::
+::::::
""")

        provider = UserProvider(passwd_file=passwd_file,
                                group_file=self.group_file)
        users = provider.get_users()
        self.assertTrue(len(users), 2)
        self.assertEqual(users[0], {"username": "root",
                                    "name": u"root",
                                    "uid": 0, "enabled": True,
                                    "location": None,
                                    "home-phone": None,
                                    "work-phone": None,
                                    "primary-gid": 0})
        self.assertEqual(users[1], {"username": "kevin",
                                    "name": u"Kevin",
                                    "uid": 1001,
                                    "enabled": True,
                                    "location": u"101",
                                    "home-phone": u"+44123124",
                                    "work-phone": u"+44123123",
                                    "primary-gid": 65534})
        log = ("WARNING: passwd file %s is incorrectly formatted" %
               passwd_file)
        self.assertTrue(log not in self.logfile.getvalue())

    def test_get_groups_incorrect_groups_file(self):
        """
        This tests the functionality for parsing /etc/group style files.

        Incorrectly formatted lines according to group(5) should be ignored
        during processing.
        """
        group_file = self.makeFile("""\
root:x:0:
cdrom:x:24:
kevin:x:kevin:
""")
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=group_file)
        groups = provider.get_groups()
        self.assertEqual(groups[0], {"name": u"root", "gid": 0,
                                     "members": []})
        self.assertEqual(groups[1], {"name": u"cdrom", "gid": 24,
                                     "members": []})
        log = ("WARNING: group file %s is incorrectly "
               "formatted: line 3." % group_file)
        self.assertIn(log, self.logfile.getvalue())

    def test_get_groups_nis_line(self):
        """
        This tests the functionality for parsing /etc/group style files.

        We should ignore the specific pattern for NIS user-extensions in
        group files.
        """
        group_file = self.makeFile("""\
root:x:0:
cdrom:x:24:
+jkakar:::
-radix:::
+:::
""")
        provider = UserProvider(passwd_file=self.passwd_file,
                                group_file=group_file)
        groups = provider.get_groups()
        self.assertEqual(groups[0], {"name": u"root", "gid": 0,
                                     "members": []})
        log = ("WARNING: group file %s is incorrectly formatted" % group_file)
        self.assertTrue(log not in self.logfile.getvalue())
