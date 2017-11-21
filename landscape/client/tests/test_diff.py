from landscape.client.diff import diff
from landscape.client.tests.helpers import LandscapeTest


class DiffTest(LandscapeTest):

    def test_empty(self):
        self.assertEqual(diff({}, {}), ({}, {}, {}))

    def test_identical(self):
        data = {"str": "wubble", "strlist": ["foo", "bar"]}
        self.assertEqual(diff(data, data), ({}, {}, {}))

    def test_create(self):
        old = {}
        new = {"str": "wubble"}
        self.assertEqual(diff(old, new), ({"str": "wubble"}, {}, {}))

    def test_update(self):
        old = {"str": "wubble"}
        new = {"str": "ooga"}
        self.assertEqual(diff(old, new), ({}, {"str": "ooga"}, {}))

    def test_delete(self):
        old = {"str": "wubble"}
        new = {}
        self.assertEqual(diff(old, new), ({}, {}, {"str": "wubble"}))

    def test_complex(self):
        old = {"str": "wubble", "int": 10}
        new = {"strlist": ["foo", "bar"], "int": 25}
        self.assertEqual(diff(old, new), ({"strlist": ["foo", "bar"]},
                                          {"int": 25},
                                          {"str": "wubble"}))
