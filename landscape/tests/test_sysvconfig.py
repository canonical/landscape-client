import time
import os

from landscape.tests.helpers import LandscapeTest

from landscape.sysvconfig import SysVConfig, ProcessError


class SysVConfigTest(LandscapeTest):

    def test_set_to_run_on_boot(self):
        filename = self.makeFile("RUN=0\n")
        sysvconfig = SysVConfig(filename)
        sysvconfig.set_start_on_boot(True)
        self.assertEquals(file(filename, "r").read(), "RUN=1\n")
        
    def test_set_to_not_run_on_boot(self):
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        sysvconfig.set_start_on_boot(False)
        self.assertEquals(file(filename, "r").read(), "RUN=0\n")

    def test_is_landscape_configured_to_run(self):
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        self.assertTrue(sysvconfig.is_configured_to_run(), True)

    def test_is_landscape_configured_to_run(self):
        filename = self.makeFile("RUN=0\n")
        sysvconfig = SysVConfig(filename)
        self.assertTrue(sysvconfig.is_configured_to_run(), False)

    def test_run_landscape(self):
        system = self.mocker.replace("os.system")
        system("/etc/init.d/landscape-client start")
        self.mocker.replay()
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        sysvconfig.start_landscape()

    def test_run_landscape_with_error(self):
        system = self.mocker.replace("os.system")
        system("/etc/init.d/landscape-client start")
        self.mocker.result(-1)
        self.mocker.replay()
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        self.assertRaises(ProcessError, sysvconfig.start_landscape)

    def test_stop_landscape(self):
        system = self.mocker.replace("os.system")
        system("/etc/init.d/landscape-client stop")
        self.mocker.replay()
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        sysvconfig.stop_landscape()

    def test_stop_landscape(self):
        system = self.mocker.replace("os.system")
        system("/etc/init.d/landscape-client stop")
        self.mocker.result(-1)
        self.mocker.replay()
        filename = self.makeFile("RUN=1\n")
        sysvconfig = SysVConfig(filename)
        self.assertRaises(ProcessError, sysvconfig.stop_landscape)
