import os

from landscape.tests.helpers import LandscapeTest

from landscape.lib.fs import append_file, read_file, touch_file


class ReadFileTest(LandscapeTest):

    def test_read_file(self):
        """
        With no options L{read_file} reads the whole file passed as argument.
        """
        path = self.makeFile("foo")
        self.assertEqual(read_file(path), "foo")

    def test_read_file_with_limit(self):
        """
        With a positive limit L{read_file} reads only the bytes after the
        given limit.
        """
        path = self.makeFile("foo bar")
        self.assertEqual(read_file(path, limit=3), " bar")

    def test_read_file_with_negative_limit(self):
        """
        With a negative limit L{read_file} reads only the tail of the file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(read_file(path, limit=-3), "end")

    def test_read_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_file} reads the entire
        file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEqual(read_file(path, limit=100), "foo bar from end")
        self.assertEqual(read_file(path, limit=-100), "foo bar from end")


class TouchFileTest(LandscapeTest):

    def test_touch_file(self):
        """
        The L{touch_file} function touches a file, setting its last
        modification time.
        """
        path = self.makeFile()
        uname_mock = self.mocker.replace("os.utime")
        self.expect(uname_mock(path, None))
        self.mocker.replay()
        touch_file(path)
        self.assertFileContent(path, "")

    def test_touch_file_multiple_times(self):
        """
        The L{touch_file} function can be called multiple times.
        """
        path = self.makeFile()
        touch_file(path)
        touch_file(path)
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
