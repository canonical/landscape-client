from landscape.tests.helpers import LandscapeTest

from landscape.lib.fs import read_file


class ReadFileTest(LandscapeTest):

    def test_read_file(self):
        """
        With no options L{read_file} reads the whole file passed as argument.
        """
        path = self.makeFile("foo")
        self.assertEquals(read_file(path), "foo")

    def test_read_file_with_limit(self):
        """
        With a positive limit L{read_file} reads only the bytes after the
        given limit.
        """
        path = self.makeFile("foo bar")
        self.assertEquals(read_file(path, limit=3), " bar")

    def test_read_file_with_negative_limit(self):
        """
        With a negative limit L{read_file} reads only the tail of the file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEquals(read_file(path, limit=-3), "end")

    def test_read_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_file} reads the entire file.
        """
        path = self.makeFile("foo bar from end")
        self.assertEquals(read_file(path, limit=100), "foo bar from end")
        self.assertEquals(read_file(path, limit=-100), "foo bar from end")
