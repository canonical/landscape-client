import unittest

from landscape.lib.tag import is_valid_tag, is_valid_tag_list


class ValidTagTest(unittest.TestCase):

    def test_valid_tags(self):
        """Test valid tags."""
        self.assertTrue(is_valid_tag(u"london"))
        self.assertTrue(is_valid_tag(u"server"))
        self.assertTrue(is_valid_tag(u"ubuntu-server"))
        self.assertTrue(is_valid_tag(u"location-1234"))
        self.assertTrue(
            is_valid_tag(u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"))

    def test_invalid_tags(self):
        """Test invalid tags."""
        self.assertFalse(is_valid_tag(u"!!!"))
        self.assertFalse(is_valid_tag(u"location 1234"))
        self.assertFalse(is_valid_tag(u"ubuntu server"))

    def test_valid_tag_list(self):
        """Test valid taglist format strings."""
        self.assertTrue(is_valid_tag_list(u"london, server"))
        self.assertTrue(is_valid_tag_list(u"ubuntu-server,london"))
        self.assertTrue(is_valid_tag_list(u"location-1234,  server"))
        self.assertTrue(
            is_valid_tag_list(
                u"prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o, server"))

    def test_invalid_tag_list(self):
        """Test invalid taglist format strings."""
        self.assertFalse(is_valid_tag_list(u"ubuntu-server,"))
        self.assertFalse(is_valid_tag_list(u"!!!,"))
        self.assertFalse(is_valid_tag_list(u"location 1234, server"))
        self.assertFalse(is_valid_tag_list(
            u"ubuntu, server, <script>alert()</script>"))
