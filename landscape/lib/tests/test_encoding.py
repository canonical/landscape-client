# -*- coding: utf-8 -*-
import codecs
import unittest

from landscape.lib.encoding import encode_if_needed, encode_values


EXPECTED_UTF8 = codecs.encode(u"請不要刪除", "utf-8")


class EncodingTest(unittest.TestCase):

    def test_encode_if_needed_utf_string(self):
        """
        When passed an utf-8 str() instance the encode_if_needed function
        returns the same.
        """
        value = EXPECTED_UTF8
        result = encode_if_needed(value)
        self.assertEqual(value, result)

    def test_encode_if_needed_utf16_string(self):
        """
        When passed an unicode instance that is a decode()'d unicode (utf-16),
        the encode_if_needed function returns the utf-16 str() equivalent
        (in utf-8).
        """
        value = u"Alex \U0001f603"
        result = encode_if_needed(value)
        expected = b'Alex \xf0\x9f\x98\x83'
        self.assertEqual(expected, result)

    def test_encode_if_needed_utf_unicode(self):
        """
        When passed an unicode instance that is a decode()'d unicode,
        the encode_if_needed function returns the utf-8 str() equivalent.
        """
        value = u'\u8acb\u4e0d\u8981\u522a\u9664'
        result = encode_if_needed(value)
        self.assertEqual(EXPECTED_UTF8, result)

    def test_encode_if_needed_utf_unicode_string(self):
        """
        When passed an encoded() unicode instance, the encode_if_needed
        function returns the utf-8 str() equivalent.
        """
        value = u"請不要刪除"
        result = encode_if_needed(value)
        self.assertEqual(EXPECTED_UTF8, result)

    def test_encode_if_needed_with_null_value(self):
        """
        When passed None, the encode_if_needed function returns None.
        """
        self.assertIs(None, encode_if_needed(None))

    def test_encode_values(self):
        """
        When passed in a dictionary, all unicode is encoded and bytes are left.
        """
        original = {"a": b"Alex \xf0\x9f\x98\x83", "b": u"Alex \U0001f603"}
        expected = {"a": b"Alex \xf0\x9f\x98\x83",
                    "b": b"Alex \xf0\x9f\x98\x83"}
        self.assertEqual(expected, encode_values(original))
