import os

from landscape.sysinfo.sysinfo import SysInfoPluginRegistry
from landscape.sysinfo.temperature import Temperature
from landscape.lib.tests.test_sysstats import ThermalZoneTest


class TemperatureTest(ThermalZoneTest):

    def setUp(self):
        super(TemperatureTest, self).setUp()
        self.temperature = Temperature(self.thermal_zone_path)
        self.sysinfo = SysInfoPluginRegistry()
        self.sysinfo.add(self.temperature)

    def test_run_returns_succeeded_deferred(self):
        self.assertDeferredSucceeded(self.temperature.run())

    def test_run_adds_header(self):
        self.write_thermal_zone("THM0", "51 C")
        self.temperature.run()
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Temperature", "51 C")])

    def test_ignores_bad_files(self):
        self.write_thermal_zone("THM0", "")
        temperature_path = os.path.join(self.thermal_zone_path,
                                        "THM0/temperature")
        file = open(temperature_path, "w")
        file.write("bad-label: 51 C")
        file.close()
        self.temperature.run()
        self.assertEqual(self.sysinfo.get_headers(), [])

    def test_ignores_unknown_formats(self):
        self.write_thermal_zone("THM0", "FOO C")
        self.temperature.run()
        self.assertEqual(self.sysinfo.get_headers(), [])

    def test_picks_highest_temperature(self):
        self.write_thermal_zone("THM0", "51 C")
        self.write_thermal_zone("THM1", "53 C")
        self.write_thermal_zone("THM2", "52 C")
        self.temperature.run()
        self.assertEqual(self.sysinfo.get_headers(),
                         [("Temperature", "53 C")])
