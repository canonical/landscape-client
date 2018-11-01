# -*- coding: utf-8 -*-
import codecs
import os
from mock import patch
import time
import unittest

from twisted.python.compat import long

from landscape.lib import testing
from landscape.lib.fs import append_text_file, append_binary_file, touch_file
from landscape.lib.fs import read_text_file, read_binary_file


class BaseTestCase(testing.FSTestCase, unittest.TestCase):
    pass


class ReadFileTest(BaseTestCase):

    def test_read_binary_file(self):
        """
        With no options L{read_binary_file} reads the whole file passed as
        argument.
        """
        path = self.makeFile("foo")
        self.assertEqual(read_binary_file(path), b"foo")

    def test_read_binary_file_with_limit(self):
        """
        With a positive limit L{read_binary_file} reads up to L{limit} bytes
        from the start of the file.
        """
        path = self.makeFile("foo bar")
        self.assertEqual(read_binary_file(path, limit=3), b"foo")

    def test_read_binary_file_with_negative_limit(self):
        """
        With a negative limit L{read_binary_file} reads only the tail of the
        file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(read_binary_file(path, limit=-3), b"end")

    def test_read_binary_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_binary_file} reads the
        entire file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(
            read_binary_file(path, limit=100), b"foo bar from end")
        self.assertEqual(
            read_binary_file(path, limit=-100), b"foo bar from end")

    def test_read_text_file(self):
        """
        With no options L{read_text_file} reads the whole file passed as
        argument as string decoded with utf-8.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path), u"foo ☃")

    def test_read_text_file_with_limit(self):
        """
        With a positive limit L{read_text_file} returns up to L{limit}
        characters from the start of the file.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=3), u"foo")

    def test_read_text_file_with_negative_limit(self):
        """
        With a negative limit L{read_text_file} reads only the tail characters
        of the string.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN} bar", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=-5), u"☃ bar")

    def test_read_text_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_text_file} reads the entire
        file.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN} bar", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=100), u"foo ☃ bar")
        self.assertEqual(read_text_file(path, limit=-100), u"foo ☃ bar")

    def test_read_text_file_with_broken_utf8(self):
        """
        A text file containing broken UTF-8 shouldn't cause an error, just
        return some sensible replacement chars.
        """
        not_quite_utf8_content = b'foo \xca\xff bar'
        path = self.makeFile(not_quite_utf8_content, mode='wb')
        self.assertEqual(read_text_file(path), u'foo \ufffd\ufffd bar')
        self.assertEqual(read_text_file(path, limit=5), u'foo \ufffd')
        self.assertEqual(read_text_file(path, limit=-3), u'bar')


class TouchFileTest(BaseTestCase):

    @patch("os.utime")
    def test_touch_file(self, utime_mock):
        """
        The L{touch_file} function touches a file, setting its last
        modification time.
        """
        path = self.makeFile()
        touch_file(path)
        utime_mock.assert_called_once_with(path, None)
        self.assertFileContent(path, b"")

    def test_touch_file_multiple_times(self):
        """
        The L{touch_file} function can be called multiple times.
        """
        path = self.makeFile()
        touch_file(path)
        touch_file(path)
        self.assertFileContent(path, b"")

    def test_touch_file_with_offset_seconds(self):
        """
        The L{touch_file} function can be called with a offset in seconds that
        will be reflected in the access and modification times of the file.
        """
        path = self.makeFile()
        current_time = long(time.time())
        expected_time = current_time - 1

        with patch.object(
                time, "time", return_value=current_time) as time_mock:
            with patch.object(os, "utime") as utime_mock:
                touch_file(path, offset_seconds=-1)

        time_mock.assert_called_once_with()
        utime_mock.assert_called_once_with(
            path, (expected_time, expected_time))

        self.assertFileContent(path, b"")


class AppendFileTest(BaseTestCase):

    def test_append_existing_text_file(self):
        """
        The L{append_text_file} function appends contents to an existing file.
        """
        existing_file = self.makeFile("foo bar")
        append_text_file(existing_file, u" baz ☃")
        self.assertFileContent(existing_file, b"foo bar baz \xe2\x98\x83")

    def test_append_text_no_file(self):
        """
        The L{append_text_file} function creates a new file if one doesn't
        exist already.
        """
        new_file = os.path.join(self.makeDir(), "new_file")
        append_text_file(new_file, u"contents ☃")
        self.assertFileContent(new_file, b"contents \xe2\x98\x83")

    def test_append_existing_binary_file(self):
        """
        The L{append_text_file} function appends contents to an existing file.
        """
        existing_file = self.makeFile("foo bar")
        append_binary_file(existing_file, b" baz \xe2\x98\x83")
        self.assertFileContent(existing_file, b"foo bar baz \xe2\x98\x83")

    def test_append_binary_no_file(self):
        """
        The L{append_text_file} function creates a new file if one doesn't
        exist already.
        """
        new_file = os.path.join(self.makeDir(), "new_file")
        append_binary_file(new_file, b"contents \xe2\x98\x83")
        self.assertFileContent(new_file, b"contents \xe2\x98\x83")
