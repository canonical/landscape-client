import os
import subprocess
import textwrap

from landscape.client import lockfile
from landscape.client.tests.helpers import LandscapeTest


class LockFileTest(LandscapeTest):

    def test_read_process_name(self):
        app = self.makeFile(textwrap.dedent("""\
            #!/usr/bin/python3
            import time
            time.sleep(10)
        """), basename="my_fancy_app")
        os.chmod(app, 0o755)
        call = subprocess.Popen([app])
        self.addCleanup(call.terminate)
        proc_name = lockfile.get_process_name(call.pid)
        self.assertEqual("my_fancy_app", proc_name)
