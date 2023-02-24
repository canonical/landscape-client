import unittest

from landscape.lib.tag import is_valid_tag
from landscape.lib.tag import is_valid_tag_list


class ValidTagTest(unittest.TestCase):
    def test_valid_tags(self):
        """Test valid tags."""
        self.assertTrue(is_valid_tag("london"))
        self.assertTrue(is_valid_tag("server"))
        self.assertTrue(is_valid_tag("ubuntu-server"))
        self.assertTrue(is_valid_tag("location-1234"))
        self.assertTrue(
            is_valid_tag("prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o"),
        )

    def test_invalid_tags(self):
        """Test invalid tags."""
        self.assertFalse(is_valid_tag("!!!"))
        self.assertFalse(is_valid_tag("location 1234"))
        self.assertFalse(is_valid_tag("ubuntu server"))

    def test_valid_tag_list(self):
        """Test valid taglist format strings."""
        self.assertTrue(is_valid_tag_list("london, server"))
        self.assertTrue(is_valid_tag_list("ubuntu-server,london"))
        self.assertTrue(is_valid_tag_list("location-1234,  server"))
        self.assertTrue(
            is_valid_tag_list(
                "prova\N{LATIN SMALL LETTER J WITH CIRCUMFLEX}o, server",
            ),
        )

    def test_invalid_tag_list(self):
        """Test invalid taglist format strings."""
        self.assertFalse(is_valid_tag_list("ubuntu-server,"))
        self.assertFalse(is_valid_tag_list("!!!,"))
        self.assertFalse(is_valid_tag_list("location 1234, server"))
        self.assertFalse(
            is_valid_tag_list("ubuntu, server, <script>alert()</script>"),
        )
