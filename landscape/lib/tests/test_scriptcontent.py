import unittest

from landscape.lib.scriptcontent import (build_script, generate_script_hash)


class ScriptContentTest(unittest.TestCase):

    def test_concatenate(self):
        self.assertEqual(build_script(u"/bin/sh", u"echo 1.0\n"),
                         "#!/bin/sh\necho 1.0\n")

    def test_concatenate_null_strings(self):
        self.assertEqual(build_script(None, None),
                         "#!\n")

    def test_generate_script_hash(self):
        hash1 = generate_script_hash("#!/bin/sh\necho 1.0\n")
        hash2 = generate_script_hash("#!/bin/sh\necho 1.0\n")
        hash3 = generate_script_hash("#!/bin/sh\necho 3.0\n")

        self.assertEqual(hash1, hash2)
        self.assertNotEqual(hash1, hash3)
        self.assertTrue(isinstance(hash1, bytes))
