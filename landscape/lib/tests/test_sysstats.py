from datetime import datetime
import os
import re
import unittest

from landscape.lib import testing
from landscape.lib.sysstats import (
    MemoryStats, CommandError, get_logged_in_users, get_uptime,
    get_thermal_zones, LoginInfoReader, BootTimes)
from landscape.lib.testing import append_login_data


SAMPLE_MEMORY_INFO = """
MemTotal:      1546436 kB
MemFree:         23452 kB
Buffers:         41656 kB
Cached:         807628 kB
SwapCached:      17572 kB
Active:        1030792 kB
Inactive:       426892 kB
HighTotal:           0 kB
HighFree:            0 kB
LowTotal:      1546436 kB
LowFree:         23452 kB
SwapTotal:     1622524 kB
SwapFree:      1604936 kB
Dirty:            1956 kB
Writeback:           0 kB
Mapped:         661772 kB
Slab:            54980 kB
CommitLimit:   2395740 kB
Committed_AS:  1566888 kB
PageTables:       2728 kB
VmallocTotal:   516088 kB
VmallocUsed:      5660 kB
VmallocChunk:   510252 kB
"""


class BaseTestCase(testing.TwistedTestCase, testing.FSTestCase,
                   unittest.TestCase):
    pass


class MemoryStatsTest(BaseTestCase):

    def test_get_memory_info(self):
        filename = self.makeFile(SAMPLE_MEMORY_INFO)
        memstats = MemoryStats(filename)
        self.assertEqual(memstats.total_memory, 1510)
        self.assertEqual(memstats.free_memory, 852)
        self.assertEqual(memstats.used_memory, 658)
        self.assertEqual(memstats.total_swap, 1584)
        self.assertEqual(memstats.free_swap, 1567)
        self.assertEqual(memstats.used_swap, 17)
        self.assertEqual("%.2f" % memstats.free_memory_percentage, "56.42")
        self.assertEqual("%.2f" % memstats.free_swap_percentage, "98.93")
        self.assertEqual("%.2f" % memstats.used_memory_percentage, "43.58")
        self.assertEqual("%.2f" % memstats.used_swap_percentage, "1.07")

    def test_get_memory_info_without_swap(self):
        sample = re.subn(r"Swap(Free|Total): *\d+ kB", r"Swap\1:       0",
                         SAMPLE_MEMORY_INFO)[0]
        filename = self.makeFile(sample)
        memstats = MemoryStats(filename)
        self.assertEqual(memstats.total_swap, 0)
        self.assertEqual(memstats.free_swap, 0)
        self.assertEqual(memstats.used_swap, 0)
        self.assertEqual(memstats.used_swap_percentage, 0)
        self.assertEqual(memstats.free_swap_percentage, 0)
        self.assertEqual(type(memstats.used_swap_percentage), float)
        self.assertEqual(type(memstats.free_swap_percentage), float)


class FakeWhoQTest(testing.HelperTestCase, BaseTestCase):

    helpers = [testing.EnvironSaverHelper]

    def fake_who(self, users):
        dirname = self.makeDir()
        os.environ["PATH"] = "%s:%s" % (dirname, os.environ["PATH"])

        self.who_path = os.path.join(dirname, "who")
        who = open(self.who_path, "w")
        who.write("#!/bin/sh\n")
        who.write("test x$1 = x-q || echo missing-parameter\n")
        who.write("echo %s\n" % users)
        who.write("echo '# users=%d'\n" % len(users.split()))
        who.close()

        os.chmod(self.who_path, 0o770)


class LoggedInUsersTest(FakeWhoQTest):

    def test_one_user(self):
        self.fake_who("joe")
        result = get_logged_in_users()
        result.addCallback(self.assertEqual, ["joe"])
        return result

    def test_one_user_multiple_times(self):
        self.fake_who("joe joe joe joe")
        result = get_logged_in_users()
        result.addCallback(self.assertEqual, ["joe"])
        return result

    def test_many_users(self):
        self.fake_who("joe moe boe doe")
        result = get_logged_in_users()
        result.addCallback(self.assertEqual, ["boe", "doe", "joe", "moe"])
        return result

    def test_command_error(self):
        self.fake_who("")
        who = open(self.who_path, "w")
        who.write("#!/bin/sh\necho ERROR 1>&2\nexit 1\n")
        who.close()
        result = get_logged_in_users()

        def assert_failure(failure):
            failure.trap(CommandError)
            self.assertEqual(str(failure.value), "ERROR\n")
        result.addErrback(assert_failure)
        return result


class UptimeTest(BaseTestCase):
    """Test for parsing /proc/uptime data."""

    def test_valid_uptime_file(self):
        """Test ensures that we can read a valid /proc/uptime file."""
        proc_file = self.makeFile("17608.24 16179.25")
        self.assertEqual("%0.2f" % get_uptime(proc_file),
                         "17608.24")


class ProcfsThermalZoneTest(BaseTestCase):

    def setUp(self):
        super(ProcfsThermalZoneTest, self).setUp()
        self.thermal_zone_path = self.makeDir()

    def get_thermal_zones(self):
        return list(get_thermal_zones(self.thermal_zone_path))

    def write_thermal_zone(self, name, temperature):
        zone_path = os.path.join(self.thermal_zone_path, name)
        if not os.path.isdir(zone_path):
            os.mkdir(zone_path)
        file = open(os.path.join(zone_path, "temperature"), "w")
        file.write("temperature:             " + temperature)
        file.close()


class GetProcfsThermalZonesTest(ProcfsThermalZoneTest):

    def test_non_existent_thermal_zone_directory(self):
        thermal_zones = list(get_thermal_zones("/non-existent/thermal_zone"))
        self.assertEqual(thermal_zones, [])

    def test_empty_thermal_zone_directory(self):
        self.assertEqual(self.get_thermal_zones(), [])

    def test_one_thermal_zone(self):
        self.write_thermal_zone("THM0", "50 C")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)

        self.assertEqual(thermal_zones[0].name, "THM0")
        self.assertEqual(thermal_zones[0].temperature, "50 C")
        self.assertEqual(thermal_zones[0].temperature_value, 50)
        self.assertEqual(thermal_zones[0].temperature_unit, "C")
        self.assertEqual(thermal_zones[0].path,
                         os.path.join(self.thermal_zone_path, "THM0"))

    def test_two_thermal_zones(self):
        self.write_thermal_zone("THM0", "50 C")
        self.write_thermal_zone("THM1", "51 C")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 2)
        self.assertEqual(thermal_zones[0].temperature, "50 C")
        self.assertEqual(thermal_zones[0].temperature_value, 50)
        self.assertEqual(thermal_zones[0].temperature_unit, "C")
        self.assertEqual(thermal_zones[1].temperature, "51 C")
        self.assertEqual(thermal_zones[1].temperature_value, 51)
        self.assertEqual(thermal_zones[1].temperature_unit, "C")

    def test_badly_formatted_temperature(self):
        self.write_thermal_zone("THM0", "SOMETHING BAD")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)
        self.assertEqual(thermal_zones[0].temperature, "SOMETHING BAD")
        self.assertEqual(thermal_zones[0].temperature_value, None)
        self.assertEqual(thermal_zones[0].temperature_unit, None)

    def test_badly_formatted_with_missing_space(self):
        self.write_thermal_zone("THM0", "SOMETHINGBAD")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)
        self.assertEqual(thermal_zones[0].temperature, "SOMETHINGBAD")
        self.assertEqual(thermal_zones[0].temperature_value, None)
        self.assertEqual(thermal_zones[0].temperature_unit, None)

    def test_temperature_file_with_missing_label(self):
        self.write_thermal_zone("THM0", "SOMETHINGBAD")
        temperature_path = os.path.join(self.thermal_zone_path,
                                        "THM0/temperature")
        file = open(temperature_path, "w")
        file.write("bad-label: foo bar\n")
        file.close()
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)
        self.assertEqual(thermal_zones[0].temperature, None)
        self.assertEqual(thermal_zones[0].temperature_value, None)
        self.assertEqual(thermal_zones[0].temperature_unit, None)


class ThermalZoneTest(BaseTestCase):

    def setUp(self):
        super(ThermalZoneTest, self).setUp()
        self.thermal_zone_path = self.makeDir()

    def get_thermal_zones(self):
        return list(get_thermal_zones(self.thermal_zone_path))

    def write_thermal_zone(self, name, temperature):
        zone_path = os.path.join(self.thermal_zone_path, name)
        if not os.path.isdir(zone_path):
            os.mkdir(zone_path)
        file = open(os.path.join(zone_path, "temp"), "w")
        file.write(temperature)
        file.close()


class GetSysfsThermalZonesTest(ThermalZoneTest):

    def test_non_existent_thermal_zone_directory(self):
        thermal_zones = list(get_thermal_zones("/non-existent/thermal_zone"))
        self.assertEqual(thermal_zones, [])

    def test_empty_thermal_zone_directory(self):
        self.assertEqual(self.get_thermal_zones(), [])

    def test_one_thermal_zone(self):
        self.write_thermal_zone("THM0", "50000")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)

        self.assertEqual(thermal_zones[0].name, "THM0")
        self.assertEqual(thermal_zones[0].temperature, "50.0 C")
        self.assertEqual(thermal_zones[0].temperature_value, 50.0)
        self.assertEqual(thermal_zones[0].temperature_unit, "C")
        self.assertEqual(thermal_zones[0].path,
                         os.path.join(self.thermal_zone_path, "THM0"))

    def test_two_thermal_zones(self):
        self.write_thermal_zone("THM0", "50000")
        self.write_thermal_zone("THM1", "51000")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 2)
        self.assertEqual(thermal_zones[0].temperature, "50.0 C")
        self.assertEqual(thermal_zones[0].temperature_value, 50.0)
        self.assertEqual(thermal_zones[0].temperature_unit, "C")
        self.assertEqual(thermal_zones[1].temperature, "51.0 C")
        self.assertEqual(thermal_zones[1].temperature_value, 51.0)
        self.assertEqual(thermal_zones[1].temperature_unit, "C")

    def test_non_int_temperature(self):
        self.write_thermal_zone("THM0", "50432")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)

        self.assertEqual(thermal_zones[0].name, "THM0")
        self.assertEqual(thermal_zones[0].temperature, "50.4 C")
        self.assertEqual(thermal_zones[0].temperature_value, 50.432)
        self.assertEqual(thermal_zones[0].temperature_unit, "C")
        self.assertEqual(thermal_zones[0].path,
                         os.path.join(self.thermal_zone_path, "THM0"))

    def test_badly_formatted_temperature(self):
        self.write_thermal_zone("THM0", "SOMETHING BAD")
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)
        self.assertEqual(thermal_zones[0].temperature, None)
        self.assertEqual(thermal_zones[0].temperature_value, None)
        self.assertEqual(thermal_zones[0].temperature_unit, None)

    def test_read_error(self):
        self.write_thermal_zone("THM0", "50000")
        temperature_path = os.path.join(self.thermal_zone_path,
                                        "THM0/temp")
        os.chmod(temperature_path, 0o200)  # --w-------
        thermal_zones = self.get_thermal_zones()
        self.assertEqual(len(thermal_zones), 1)
        self.assertEqual(thermal_zones[0].temperature, None)
        self.assertEqual(thermal_zones[0].temperature_value, None)
        self.assertEqual(thermal_zones[0].temperature_unit, None)


class LoginInfoReaderTest(BaseTestCase):
    """Tests for login info file reader."""

    def test_read_empty_file(self):
        """Test ensures the reader is resilient to empty files."""
        filename = self.makeFile("")

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)
            self.assertEqual(reader.read_next(), None)
        finally:
            file.close()

    def test_read_login_info(self):
        """Test ensures the reader can read login info."""
        filename = self.makeFile("")
        append_login_data(filename, login_type=1, pid=100, tty_device="/dev/",
                          id="1", username="jkakar", hostname="localhost",
                          termination_status=0, exit_status=0, session_id=1,
                          entry_time_seconds=105, entry_time_milliseconds=10,
                          remote_ip_address=[192, 168, 42, 102])
        append_login_data(filename, login_type=1, pid=101, tty_device="/dev/",
                          id="1", username="root", hostname="localhost",
                          termination_status=0, exit_status=0, session_id=2,
                          entry_time_seconds=235, entry_time_milliseconds=17,
                          remote_ip_address=[192, 168, 42, 102])

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)

            info = reader.read_next()
            self.assertEqual(info.login_type, 1)
            self.assertEqual(info.pid, 100)
            self.assertEqual(info.tty_device, "/dev/")
            self.assertEqual(info.id, "1")
            self.assertEqual(info.username, "jkakar")
            self.assertEqual(info.hostname, "localhost")
            self.assertEqual(info.termination_status, 0)
            self.assertEqual(info.exit_status, 0)
            self.assertEqual(info.session_id, 1)
            self.assertEqual(info.entry_time, datetime.utcfromtimestamp(105))
            # FIXME Test IP address handling. -jk

            info = reader.read_next()
            self.assertEqual(info.login_type, 1)
            self.assertEqual(info.pid, 101)
            self.assertEqual(info.tty_device, "/dev/")
            self.assertEqual(info.id, "1")
            self.assertEqual(info.username, "root")
            self.assertEqual(info.hostname, "localhost")
            self.assertEqual(info.termination_status, 0)
            self.assertEqual(info.exit_status, 0)
            self.assertEqual(info.session_id, 2)
            self.assertEqual(info.entry_time, datetime.utcfromtimestamp(235))
            # FIXME Test IP address handling. -jk

            info = reader.read_next()
            self.assertEqual(info, None)
        finally:
            file.close()

    def test_login_info_iterator(self):
        """Test ensures iteration behaves correctly."""
        filename = self.makeFile("")
        append_login_data(filename)
        append_login_data(filename)

        file = open(filename, "rb")
        try:
            reader = LoginInfoReader(file)
            count = 0

            for info in reader.login_info():
                count += 1

            self.assertEqual(count, 2)
        finally:
            file.close()


class BootTimesTest(BaseTestCase):

    def test_fallback_to_uptime(self):
        """
        When no data is available in C{/var/log/wtmp}
        L{BootTimes.get_last_boot_time} falls back to C{/proc/uptime}.
        """
        wtmp_filename = self.makeFile("")
        append_login_data(wtmp_filename, tty_device="~", username="shutdown",
                          entry_time_seconds=535)
        self.assertTrue(BootTimes(filename=wtmp_filename).get_last_boot_time())
