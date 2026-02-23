from landscape.client import lockfile
from landscape.client.tests.helpers import LandscapeTest, ready_subprocess


class LockFileTest(LandscapeTest):
    def test_read_process_name(self):
        with ready_subprocess(self, "my_fancy_app") as call:
            proc_name = lockfile.get_process_name(call.pid)
            self.assertEqual("my_fancy_app", proc_name)
