# -*- coding: utf-8 -*-

from landscape.tests.helpers import LandscapeTest
from landscape.lib.encoding import encode_if_needed, encode_dict_if_needed


class EncodingTest(LandscapeTest):

    def test_encode_if_needed_utf_string(self):
        """
        When passed an utf-8 str() instance the encode_if_needed function
        returns the same.
        """
        # "請不要刪除"
        value = b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4'
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
        # "請不要刪除"
        expected = (
            b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4')
        result = encode_if_needed(value)
        self.assertEqual(expected, result)

    def test_encode_if_needed_utf_unicode_string(self):
        """
        When passed an encoded() unicode instance, the encode_if_needed
        function returns the utf-8 str() equivalent.
        """
        value = u"請不要刪除"
        expected = (
            b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4')
        result = encode_if_needed(value)
        self.assertEqual(expected, result)

    def test_encode_if_needed_with_null_value(self):
        """
        When passed None, the encode_if_needed function returns None.
        """
        self.assertIs(None, encode_if_needed(None))

    def test_encode_dict_if_needed(self):
        """
        The encode_dict_if_needed function returns a dict for which every
        value was passed to the encode_if_needed function.
        """
        value = {"a": "請不要刪除", "b": u'\u8acb\u4e0d\u8981\u522a\u9664',
                 "c": u"請不要刪除", "d": None, "e": 123}
        expected = {
            "a":
            b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4',
            "b":
            b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4',
            "c":
            b'\xe8\xab\x8b\xe4\xb8\x8d\xe8\xa6\x81\xe5\x88\xaa\xe9\x99\xa4',
            "d": None,
            "e": 123
        }
        result = encode_dict_if_needed(value)
        self.assertEqual(expected, result)
