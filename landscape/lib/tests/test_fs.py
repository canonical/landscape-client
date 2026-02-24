import codecs
import os
import time
import unittest
from unittest.mock import patch

from landscape.lib import testing
from landscape.lib.fs import (
    append_binary_file,
    append_text_file,
    create_binary_file,
    create_text_file,
    read_binary_file,
    read_text_file,
    touch_file,
)


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
            read_binary_file(path, limit=100),
            b"foo bar from end",
        )
        self.assertEqual(
            read_binary_file(path, limit=-100),
            b"foo bar from end",
        )

    def test_read_text_file(self):
        """
        With no options L{read_text_file} reads the whole file passed as
        argument as string decoded with utf-8.
        """
        utf8_content = codecs.encode("foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path), "foo ☃")

    def test_read_text_file_with_limit(self):
        """
        With a positive limit L{read_text_file} returns up to L{limit}
        characters from the start of the file.
        """
        utf8_content = codecs.encode("foo \N{SNOWMAN}", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=3), "foo")

    def test_read_text_file_with_negative_limit(self):
        """
        With a negative limit L{read_text_file} reads only the tail characters
        of the string.
        """
        utf8_content = codecs.encode("foo \N{SNOWMAN} bar", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=-5), "☃ bar")

    def test_read_text_file_with_limit_bigger_than_file(self):
        """
        If the limit is bigger than the file L{read_text_file} reads the entire
        file.
        """
        utf8_content = codecs.encode("foo \N{SNOWMAN} bar", "utf-8")
        path = self.makeFile(utf8_content, mode="wb")
        self.assertEqual(read_text_file(path, limit=100), "foo ☃ bar")
        self.assertEqual(read_text_file(path, limit=-100), "foo ☃ bar")

    def test_read_text_file_with_broken_utf8(self):
        """
        A text file containing broken UTF-8 shouldn't cause an error, just
        return some sensible replacement chars.
        """
        not_quite_utf8_content = b"foo \xca\xff bar"
        path = self.makeFile(not_quite_utf8_content, mode="wb")
        self.assertEqual(read_text_file(path), "foo \ufffd\ufffd bar")
        self.assertEqual(read_text_file(path, limit=5), "foo \ufffd")
        self.assertEqual(read_text_file(path, limit=-3), "bar")


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
        current_time = int(time.time())
        expected_time = current_time - 1

        with (
            patch.object(
                time,
                "time",
                return_value=current_time,
            ) as time_mock,
            patch.object(os, "utime") as utime_mock,
        ):
            touch_file(path, offset_seconds=-1)

        time_mock.assert_called_once_with()
        utime_mock.assert_called_once_with(
            path,
            (expected_time, expected_time),
        )

        self.assertFileContent(path, b"")

    def test_touch_file_with_mode(self):
        path = self.makeFile(content="")
        original_mode = os.stat(path).st_mode & 0o777
        new_mode = 0o666
        self.assertNotEqual(original_mode, new_mode)

        touch_file(path, mode=new_mode)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(new_mode, actual_mode)

    def test_touch_file_with_mode_none(self):
        path = self.makeFile(content="")
        original_mode = os.stat(path).st_mode & 0o777

        touch_file(path, mode=None)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(original_mode, actual_mode)

    def test_touch_file_creates_new_empty_file(self):
        path = self.makeDir() + "new_file"

        with self.assertRaises(FileNotFoundError):
            os.stat(path)

        touch_file(path)

        with open(path, "rb") as f:
            content = f.read()
        self.assertEqual(b"", content)

    def test_touch_file_creates_new_file_with_mode(self):
        path = self.makeDir() + "new_file"
        mode = 0o666

        with self.assertRaises(FileNotFoundError):
            os.stat(path)

        touch_file(path, mode=mode)

        with open(path, "rb") as f:
            content = f.read()
        self.assertEqual(b"", content)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, actual_mode)


class AppendFileTest(BaseTestCase):
    def test_append_existing_text_file(self):
        """
        The L{append_text_file} function appends contents to an existing file.
        """
        existing_file = self.makeFile("foo bar")
        append_text_file(existing_file, " baz ☃")
        self.assertFileContent(existing_file, b"foo bar baz \xe2\x98\x83")

    def test_append_text_no_file(self):
        """
        The L{append_text_file} function creates a new file if one doesn't
        exist already.
        """
        new_file = os.path.join(self.makeDir(), "new_file")
        append_text_file(new_file, "contents ☃")
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


class TestCreateBinaryFile(BaseTestCase):
    def setUp(self):
        self.temp_dir = self.makeDir()

    def test_create_binary_file(self):
        path = os.path.join(self.temp_dir, "test.bin")
        content = b"Hello, World!"
        create_binary_file(path, content)

        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), content)

    def test_create_binary_file_with_mode(self):
        """Test creating a file with a specific mode."""
        path = os.path.join(self.temp_dir, "test_mode.bin")
        content = b"Hello, World!"
        mode = 0o600

        create_binary_file(path, content, mode=mode)

        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), content)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(actual_mode, mode)

    def test_create_binary_file_with_mode_none(self):
        path1 = os.path.join(self.temp_dir, "test_none.bin")
        path2 = os.path.join(self.temp_dir, "test_omitted.bin")
        content = b"Same content"

        create_binary_file(path1, content, mode=None)
        create_binary_file(path2, content)

        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))

        with open(path1, "rb") as f1, open(path2, "rb") as f2:
            self.assertEqual(f1.read(), f2.read())

        mode1 = os.stat(path1).st_mode & 0o777
        mode2 = os.stat(path2).st_mode & 0o777
        self.assertEqual(mode1, mode2)

    def test_create_binary_file_overwrites_existing(self):
        path = os.path.join(self.temp_dir, "overwrite.bin")
        initial_content = b"Old content"
        new_content = b"New content"
        mode = 0o600

        # Create file initially
        with open(path, "wb") as f:
            f.write(initial_content)

        # Update via function
        create_binary_file(path, new_content, mode=mode)

        with open(path, "rb") as f:
            self.assertEqual(f.read(), new_content)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(actual_mode, mode)


class TestCreateTextFile(BaseTestCase):
    def setUp(self):
        self.temp_dir = self.makeDir()

    def test_create_text_file(self):
        path = os.path.join(self.temp_dir, "test.txt")
        content = "Hello, World!"
        create_text_file(path, content)

        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            self.assertEqual(f.read(), content)

    def test_create_text_file_with_mode(self):
        """Test creating a file with a specific mode."""
        path = os.path.join(self.temp_dir, "test_mode.txt")
        content = "Hello, World!"
        mode = 0o600

        create_text_file(path, content, mode=mode)

        self.assertTrue(os.path.exists(path))
        with open(path, "r") as f:
            self.assertEqual(f.read(), content)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(actual_mode, mode)

    def test_create_text_file_with_mode_none(self):
        path1 = os.path.join(self.temp_dir, "test_none.txt")
        path2 = os.path.join(self.temp_dir, "test_omitted.txt")
        content = "Same content"

        create_text_file(path1, content, mode=None)
        create_text_file(path2, content)

        self.assertTrue(os.path.exists(path1))
        self.assertTrue(os.path.exists(path2))

        with open(path1, "r") as f1, open(path2, "r") as f2:
            self.assertEqual(f1.read(), f2.read())

        mode1 = os.stat(path1).st_mode & 0o777
        mode2 = os.stat(path2).st_mode & 0o777
        self.assertEqual(mode1, mode2)

    def test_create_text_file_overwrites_existing(self):
        path = os.path.join(self.temp_dir, "overwrite.txt")
        initial_content = "Old content"
        new_content = "New content"
        mode = 0o600

        # Create file initially
        with open(path, "w") as f:
            f.write(initial_content)

        # Update via function
        create_text_file(path, new_content, mode=mode)

        with open(path, "r") as f:
            self.assertEqual(f.read(), new_content)

        actual_mode = os.stat(path).st_mode & 0o777
        self.assertEqual(actual_mode, mode)
