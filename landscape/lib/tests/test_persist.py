import os
import pprint
import unittest

from landscape.lib import testing
from landscape.lib.persist import (
    path_string_to_tuple, path_tuple_to_string, Persist, RootedPersist,
    PickleBackend, PersistError, PersistReadOnlyError)


class PersistHelpersTest(unittest.TestCase):

    paths = [
        ("ab", ("ab",)),
        ("ab.cd", ("ab", "cd")),
        ("ab.cd.de", ("ab", "cd", "de")),
        ("ab[0]", ("ab", 0)),
        ("ab[0][1]", ("ab", 0, 1)),
        ("ab.cd[1]", ("ab", "cd", 1)),
        ("ab[0].cd[1]", ("ab", 0, "cd", 1)),
        ("ab.cd.de[2]", ("ab", "cd", "de", 2)),
        ]

    def test_path_string_to_tuple(self):
        for path_string, path_tuple in self.paths:
            self.assertEqual(path_string_to_tuple(path_string), path_tuple)

    def test_path_string_to_tuple_error(self):
        self.assertRaises(PersistError, path_string_to_tuple, "ab[0][c]")

    def test_path_tuple_to_string(self):
        for path_string, path_tuple in self.paths:
            self.assertEqual(path_tuple_to_string(path_tuple), path_string)


class BasePersistTest(unittest.TestCase):

    set_items = [
        ("ab", 1),
        ("ab", 2),
        ("cd.ef", 3.4),
        ("cd.gh", "4"),
        ("cd.gh", "5"),
        ("cd.ij.kl", (1, 2.3, "4", [5], (6,))),
        ("cd.ij.mn", [1, 2.3, "4", [5], (6,)]),
        ("cd.ij.op[1]", 0),
        ("cd.ij.op[1]", 1),
        ("cd.ij.op[2]", 2),
        ("qr", {"s": {"t": "u"}}),
        ("v", [0, {}, 2]),
        ("v[1].v", "woot"),
        ]

    set_result = {
                  "ab": 2,
                  "cd": {
                         "ef": 3.4,
                         "gh": "5",
                         "ij": {
                                "kl": (1, 2.3, "4", [5], (6,)),
                                "mn": [1, 2.3, "4", [5], (6,)],
                                "op": [0, 1, 2]
                               },
                         },
                  "qr": {"s": {"t": "u"}},
                  "v": [0, {"v": "woot"}, 2],
                 }

    get_items = [
                 ("ab", 2),
                 ("cd.ef", 3.4),
                 ("cd.gh", "5"),
                 ("cd.ij.kl", (1, 2.3, "4", [5], (6,))),
                 ("cd.ij.kl[3]", [5]),
                 ("cd.ij.kl[3][0]", 5),
                 ("cd.ij.mn", [1, 2.3, "4", [5], (6,)]),
                 ("cd.ij.mn.4", "4"),
                 ("cd.ij.mn.5", None),
                 ("cd.ij.op", [0, 1, 2]),
                 ("cd.ij.op[0]", 0),
                 ("cd.ij.op[1]", 1),
                 ("cd.ij.op[2]", 2),
                 ("cd.ij.op[3]", None),
                 ("qr", {"s": {"t": "u"}}),
                 ("qr.s", {"t": "u"}),
                 ("qr.s.t", "u"),
                 ("x", None),
                 ("x.y.z", None),
                ]

    add_items = [
                 ("ab", 1),
                 ("ab", 2.3),
                 ("ab", "4"),
                 ("ab", [5]),
                 ("ab", (6,)),
                 ("ab", {}),
                 ("ab[5].cd", "foo"),
                 ("ab[5].cd", "bar"),
                ]

    add_result = {
                  "ab": [1, 2.3, "4", [5], (6,), {"cd": ["foo", "bar"]}],
                 }

    def setUp(self):
        super(BasePersistTest, self).setUp()
        self.persist = self.build_persist()

    def tearDown(self):
        del self.persist
        super(BasePersistTest, self).tearDown()

    def build_persist(self, *args, **kwargs):
        return Persist(*args, **kwargs)

    def format(self, result, expected):
        repr_result = pprint.pformat(result)
        repr_expected = pprint.pformat(expected)
        return "\nResult:\n%s\nExpected:\n%s\n" % (repr_result, repr_expected)


class GeneralPersistTest(BasePersistTest):

    def test_set(self):
        for path, value in self.set_items:
            self.persist.set(path, value)
        result = self.persist.get((), hard=True)
        self.assertEqual(result, self.set_result,
                         self.format(result, self.set_result))

    def test_set_tuple_paths(self):
        for path, value in self.set_items:
            self.persist.set(path_string_to_tuple(path), value)
        result = self.persist.get((), hard=True)
        self.assertEqual(result, self.set_result,
                         self.format(result, self.set_result))

    def test_set_from_result(self):
        for path in self.set_result:
            self.persist.set(path, self.set_result[path])
        result = self.persist.get((), hard=True)
        self.assertEqual(result, self.set_result,
                         self.format(result, self.set_result))

    def test_get(self):
        for path in self.set_result:
            self.persist.set(path, self.set_result[path])
        for path, value in self.get_items:
            self.assertEqual(self.persist.get(path), value)

    def test_get_tuple_paths(self):
        for path in self.set_result:
            self.persist.set(path_string_to_tuple(path), self.set_result[path])
        for path, value in self.get_items:
            self.assertEqual(self.persist.get(path), value)

    def test_add(self):
        for path, value in self.add_items:
            self.persist.add(path, value)
        result = self.persist.get((), hard=True)
        self.assertEqual(result, self.add_result,
                         self.format(result, self.add_result))

    def test_add_unique(self):
        self.persist.add("a", "b")
        self.assertEqual(self.persist.get("a"), ["b"])
        self.persist.add("a", "b")
        self.assertEqual(self.persist.get("a"), ["b", "b"])
        self.persist.add("a", "b", unique=True)
        self.assertEqual(self.persist.get("a"), ["b", "b"])
        self.persist.add("a", "c", unique=True)
        self.assertEqual(self.persist.get("a"), ["b", "b", "c"])

    def test_keys(self):
        self.persist.set("a", {"b": 1, "c": {"d": 2}, "e": list("foo")})
        keys = self.persist.keys
        self.assertEqual(set(keys((), hard=True)), set(["a"]))
        self.assertEqual(set(keys("a")), set(["b", "c", "e"]))
        self.assertEqual(set(keys("a.d")), set([]))
        self.assertEqual(set(keys("a.e")), set([0, 1, 2]))
        self.assertEqual(set(keys("a.f")), set([]))
        self.assertRaises(PersistError, keys, "a.b")

    def test_has(self):
        self.persist.set("a", {"b": 1, "c": {"d": 2}, "e": list("foo")})
        has = self.persist.has
        self.assertTrue(has("a"))
        self.assertTrue(has(("a", "b")))
        self.assertTrue(has("a.c"))
        self.assertTrue(has("a.c", "d"))
        self.assertTrue(has("a.c.d"))
        self.assertTrue(has("a.e"))
        self.assertTrue(has("a.e[0]"))
        self.assertTrue(has("a.e", "f"))
        self.assertTrue(has("a.e", "o"))
        self.assertFalse(has("b"))
        self.assertFalse(has("a.f"))
        self.assertFalse(has("a.c.f"))
        self.assertFalse(has("a.e[3]"))
        self.assertFalse(has("a.e", "g"))
        self.assertRaises(PersistError, has, "a.b.c")

    def test_remove(self):
        self.persist.set("a", {"b": [1], "c": {"d": 2}, "e": list("foot")})
        get = self.persist.get
        has = self.persist.has
        remove = self.persist.remove

        self.assertFalse(remove("a.f"))

        self.assertRaises(PersistError, remove, "a.c.d.e")

        self.assertTrue(remove(("a", "e", "o")))
        self.assertEqual(get("a.e"), ["f", "t"])

        self.assertFalse(remove("a.e[2]"))
        self.assertEqual(get("a.e"), ["f", "t"])

        self.assertTrue(remove("a.e[1]"))
        self.assertEqual(get("a.e"), ["f"])

        self.assertTrue(remove("a.e", "f"))
        self.assertFalse(has("a.e"))

        self.assertFalse(remove("a.b[1]"))
        self.assertEqual(get("a.b"), [1])

        self.assertTrue(remove("a.b", 1))
        self.assertFalse(has("a.b"))

        self.assertTrue(remove("a.c"))
        self.assertFalse(has("a.c"))

        self.assertFalse(has("a"))

    def test_move(self):
        self.persist.set("a", {"b": [1], "c": {"d": 2}})

        move = self.persist.move
        get = self.persist.get

        self.assertTrue(move("a.b", "a.c.b"))
        self.assertEqual(get("a"), {"c": {"b": [1], "d": 2}})

        self.assertTrue(move("a.c.b[0]", "a.c.b"))
        self.assertEqual(get("a"), {"c": {"b": 1, "d": 2}})

        self.assertTrue(move(("a", "c", "b"), ("a", "c", "b", 0)))
        self.assertEqual(get("a"), {"c": {"b": [1], "d": 2}})

    def test_copy_values_on_set(self):
        d = {"b": 1}
        d_orig = d.copy()
        self.persist.set("a", d)
        d["c"] = 2
        self.assertEqual(self.persist.get("a"), d_orig)

    def test_copy_values_on_add(self):
        d = {"b": 1}
        d_orig = d.copy()
        self.persist.add("a", d)
        d["c"] = 2
        self.assertEqual(self.persist.get("a[0]"), d_orig)

    def test_copy_values_on_get(self):
        self.persist.set("a", {"b": 1})
        d = self.persist.get("a")
        d_orig = d.copy()
        d["c"] = 2
        self.assertEqual(self.persist.get("a"), d_orig)

    def test_root_at(self):
        rooted = self.persist.root_at("my-module")
        rooted.set("option", 1)
        self.assertEqual(self.persist.get("my-module.option"), 1)


class SaveLoadPersistTest(testing.FSTestCase, BasePersistTest):

    def makePersistFile(self, *args, **kwargs):
        return self.makeFile(*args, backupsuffix=".old", **kwargs)

    def test_readonly(self):
        self.assertFalse(self.persist.readonly)
        self.persist.readonly = True
        self.assertTrue(self.persist.readonly)
        self.persist.readonly = False
        self.assertFalse(self.persist.readonly)

        self.persist.readonly = True
        self.assertRaises(PersistReadOnlyError, self.persist.set, "ab", 2)
        self.assertRaises(PersistReadOnlyError, self.persist.add, "ab", 3)
        self.assertRaises(PersistReadOnlyError, self.persist.remove, "ab", 4)
        self.assertRaises(PersistReadOnlyError, self.persist.move, "ab", "cd")

        for keyword in ["weak", "soft"]:
            kwargs = {keyword: True}
            self.persist.set("ab", 2, **kwargs)
            self.persist.add("cd", 2, **kwargs)
            self.persist.remove("ab", **kwargs)
            self.persist.move("cd", "ef", **kwargs)

    def test_assert_writable(self):
        self.persist.assert_writable()
        self.persist.set("ab", 1)
        self.persist.readonly = True
        self.assertRaises(PersistReadOnlyError, self.persist.assert_writable)

    def test_modified(self):
        self.assertFalse(self.persist.modified)
        self.persist.set("ab", 1)
        self.assertTrue(self.persist.modified)
        self.persist.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.add("cd", 2)
        self.assertTrue(self.persist.modified)
        self.persist.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.remove("ab")
        self.assertTrue(self.persist.modified)
        self.persist.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.move("cd", "ef")
        self.assertTrue(self.persist.modified)

    def test_save_and_load(self):
        for path in self.set_result:
            self.persist.set(path, self.set_result[path])

        filename = self.makePersistFile()
        self.persist.save(filename)

        persist = self.build_persist()
        persist.load(filename)

        result = persist.get((), hard=True)
        self.assertEqual(result, self.set_result,
                         self.format(result, self.set_result))

    def test_save_on_unexistent_dir(self):
        dirname = self.makePersistFile()
        filename = os.path.join(dirname, "foobar")

        self.assertFalse(os.path.exists(dirname))
        self.persist.save(filename)
        self.assertTrue(os.path.isfile(filename))

    def test_save_creates_backup(self):
        filename = self.makePersistFile("foobar")
        filename_old = filename + ".old"

        self.assertFalse(os.path.exists(filename_old))
        self.persist.save(filename)
        self.assertTrue(os.path.exists(filename_old))

    def test_save_to_default_file(self):
        """
        Persist can be constructed with a filename, and Persist.save with no
        arguments will write to that filename.
        """
        filename = self.makePersistFile()
        persist = self.build_persist(filename=filename)
        self.assertFalse(os.path.exists(filename))
        persist.save()
        self.assertTrue(os.path.exists(filename))

    def test_save_to_no_default_file(self):
        """
        If no default filename was given, calling Persist.save with no
        arguments will raise a PersistError.
        """
        self.assertRaises(PersistError, self.persist.save)

    def test_load_default_file(self):
        """
        If a Persist is created with a default filename, and the filename
        exists, it will be loaded.
        """
        filename = self.makePersistFile()
        persist = self.build_persist(filename=filename)
        persist.set("foo", "bar")
        persist.save()

        persist = self.build_persist(filename=filename)
        self.assertEqual(persist.get("foo"), "bar")

    def test_load_restores_backup(self):
        filename = self.makePersistFile("foobar")
        filename_old = filename + ".old"

        self.persist.set("a", 1)
        self.persist.save(filename_old)

        persist = self.build_persist()
        persist.load(filename)

        self.assertEqual(persist.get("a"), 1)

    def test_load_empty_files_wont_break(self):
        filename = self.makePersistFile("")
        self.persist.load(filename)

    def test_load_empty_files_restore_backup(self):
        """
        If the current file is empty, it tries to load the old one if it
        exists.
        """
        filename = self.makePersistFile("")
        filename_old = filename + ".old"

        self.persist.set("a", 1)
        self.persist.save(filename_old)

        persist = self.build_persist()
        persist.load(filename)

        self.assertEqual(persist.get("a"), 1)

    def test_non_existing_raise_error(self):
        """
        Trying to load a file that doesn't exist result in a L{PersistError}.
        """
        persist = self.build_persist()
        self.assertRaises(PersistError, persist.load, "/nonexistent")

    def test_non_existing_restore_backup(self):
        """
        If the file doesn't exist, it tries to load the old one if present and
        valid.
        """
        filename = self.makePersistFile("")
        filename_old = filename + ".old"
        os.unlink(filename)

        self.persist.set("a", 1)
        self.persist.save(filename_old)

        persist = self.build_persist()
        persist.load(filename)

        self.assertEqual(persist.get("a"), 1)


class PicklePersistTest(GeneralPersistTest, SaveLoadPersistTest):

    def build_persist(self, *args, **kwargs):
        return Persist(PickleBackend(), *args, **kwargs)


class RootedPersistTest(GeneralPersistTest):

    def build_persist(self, *args, **kwargs):
        return RootedPersist(Persist(), "root.path", *args, **kwargs)

    def test_readonly(self):
        self.assertFalse(self.persist.readonly)
        self.assertRaises(AttributeError,
                          setattr, self.persist, "readonly", True)
        self.persist.parent.readonly = True
        self.assertTrue(self.persist.readonly)

    def test_assert_writable(self):
        self.persist.assert_writable()
        self.persist.set("ab", 1)
        self.persist.parent.readonly = True
        self.assertRaises(PersistReadOnlyError, self.persist.assert_writable)

    def test_modified(self):
        self.assertFalse(self.persist.modified)
        self.persist.set("ab", 1)
        self.assertTrue(self.persist.modified)
        self.persist.parent.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.add("cd", 2)
        self.assertTrue(self.persist.modified)
        self.persist.parent.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.remove("ab")
        self.assertTrue(self.persist.modified)
        self.persist.parent.reset_modified()
        self.assertFalse(self.persist.modified)
        self.persist.move("cd", "ef")
        self.assertTrue(self.persist.modified)
