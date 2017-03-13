# -*- coding: utf-8 -*-
import codecs
import os
from mock import patch
import time

from twisted.python.compat import long

from landscape.tests.helpers import LandscapeTest

from landscape.lib.fs import append_file, read_file, touch_file


class ReadFileTest(LandscapeTest):

    def test_read_file(self):
        """
        With no options L{read_file} reads the whole file passed as argument.
        """
        path = self.makeFile("foo")
        self.assertEqual(read_file(path), b"foo")

    def test_read_file_encoding(self):
        """
        With encoding L{read_file} reads the whole file passed as argument and
        decodes it.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_file(path, encoding="utf-8"), u"foo ☃")

    def test_read_file_with_limit(self):
        """
        With a positive limit L{read_file} reads only the bytes after the
        given limit.
        """
        path = self.makeFile("foo bar")
        self.assertEqual(read_file(path, limit=3), b" bar")

    def test_read_file_with_limit_encoding(self):
        """
        With a positive limit L{read_file} reads only the bytes after the
        given limit.
        """
        utf8_content = codecs.encode(u"foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_file(path, limit=3, encoding="utf-8"), u" ☃")

    def test_read_file_with_negative_limit(self):
        """
        With a negative limit L{read_file} reads only the tail of the file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(read_file(path, limit=-3), b"end")

    def test_read_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_file} reads the entire
        file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(read_file(path, limit=100), b"foo bar from end")
        self.assertEqual(read_file(path, limit=-100), b"foo bar from end")


class TouchFileTest(LandscapeTest):

    @patch("os.utime")
    def test_touch_file(self, utime_mock):
        """
        The L{touch_file} function touches a file, setting its last
        modification time.
        """
        path = self.makeFile()
        touch_file(path)
        utime_mock.assert_called_once_with(path, None)
        self.assertFileContent(path, "")

    def test_touch_file_multiple_times(self):
        """
        The L{touch_file} function can be called multiple times.
        """
        path = self.makeFile()
        touch_file(path)
        touch_file(path)
        self.assertFileContent(path, "")

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

        self.assertFileContent(path, "")


class AppendFileTest(LandscapeTest):

    def test_append_existing_file(self):
        """
        The L{append_file} function appends contents to an existing file.
        """
        existing_file = self.makeFile("foo bar")
        append_file(existing_file, " baz")
        self.assertFileContent(existing_file, "foo bar baz")

    def test_append_no_file(self):
        """
        The L{append_file} function creates a new file if one doesn't
        exist already.
        """
        new_file = os.path.join(self.makeDir(), "new_file")
        append_file(new_file, "contents")
        self.assertFileContent(new_file, "contents")
