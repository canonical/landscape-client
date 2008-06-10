from landscape.diff import diff
from landscape.tests.helpers import LandscapeTest


class DiffTest(LandscapeTest):

    def test_empty(self):
        self.assertEquals(diff({}, {}), ({}, {}, {}))

    def test_identical(self):
        data = {"str": "wubble", "strlist": ["foo", "bar"]}
        self.assertEquals(diff(data, data), ({}, {}, {}))

    def test_create(self):
        old = {}
        new = {"str": "wubble"}
        self.assertEquals(diff(old, new), ({"str": "wubble"}, {}, {}))

    def test_update(self):
        old = {"str": "wubble"}
        new = {"str": "ooga"}
        self.assertEquals(diff(old, new), ({}, {"str": "ooga"}, {}))

    def test_delete(self):
        old = {"str": "wubble"}
        new = {}
        self.assertEquals(diff(old, new), ({}, {}, {"str": "wubble"}))

    def test_complex(self):
        old = {"str": "wubble", "int": 10}
        new = {"strlist": ["foo", "bar"], "int": 25}
        self.assertEquals(diff(old, new), ({"strlist": ["foo", "bar"]},
                                           {"int": 25},
                                           {"str": "wubble"}))
