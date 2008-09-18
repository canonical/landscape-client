import unittest

from landscape.lib.scriptcontent import (build_script,
    generate_script_hash)

class ScriptContentTest(unittest.TestCase):

    def test_concatenate(self):
        self.assertEquals(build_script(u"/bin/sh", u"echo 1.0\n"), 
                          "#!/bin/sh\necho 1.0\n")

    def test_generate_script_hash(self):
        hash1 = generate_script_hash("#!/bin/sh\necho 1.0\n")
        hash2 = generate_script_hash("#!/bin/sh\necho 1.0\n")
        hash3 = generate_script_hash("#!/bin/sh\necho 3.0\n")

        self.assertEquals(hash1, hash2)
        self.assertNotEqual(hash1, hash3)
        self.assertTrue(isinstance(hash1, str))
