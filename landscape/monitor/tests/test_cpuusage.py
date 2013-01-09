from landscape.monitor.cpuusage import CPUUsage
from landscape.tests.helpers import LandscapeTest, MonitorHelper


class CPUUsagePluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def _write_2_stat_files(self, contents_1, contents_2):
        statfile1 = self.makeFile()
        statfile2 = self.makeFile()
        with open(statfile1, "w") as f:
            f.write(contents_1)
        with open(statfile2, "w") as f:
            f.write(contents_2)
        return (statfile1, statfile2)

    def test_get_cpu_usage_file_not_changed(self):
        """
        When the stat file did not change between calls, the
        C{_get_cpu_usage} method returns 0.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  100 100 100 100 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous mesure
        # yet.
        self.assertEqual(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertEqual(result, 0)

    def test_get_cpu_usage_multiline_files(self):
        """
        The C{_get_cpu_usage} method parses multiline stat files correctly.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0\nsome garbage"""
        contents2 = """cpu  100 100 100 100 100 100 100 0 0 0\nsome stuff"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous mesure
        # yet.
        self.assertEqual(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertEqual(result, 0)

    def test_get_cpu_usage_100_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        100%, the method returns 1.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  200 100 100 100 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous mesure
        # yet.
        self.assertEqual(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 1)

    def test_get_cpu_usage_0_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        0% (all the changes are in the idle column) the method returns 0.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  100 100 100 200 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous mesure
        # yet.
        self.assertEqual(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 0)

    def test_get_cpu_usage_50_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        50% (as much changed in an "active" column that in the idle column)
        the method returns 0.5.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  200 100 100 200 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous mesure
        # yet.
        self.assertEqual(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 0.5)

    def test_cpu_load(self):
        """
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  200 100 100 100 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)
        interval = 30
        plugin = CPUUsage(create_time=self.reactor.time, interval=interval)
        self.monitor.add(plugin)
        plugin._stat_file = thefile

        message = plugin.create_message()
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "cpu-usage")
        self.assertTrue("cpu-usages" in message)

        cpu_usages = message["cpu-usages"]
        self.assertEqual(len(cpu_usages), 0)

        # Trigger a plugin run
        self.reactor.advance(interval)

        message = plugin.create_message()
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "cpu-usage")
        self.assertTrue("cpu-usages" in message)

        cpu_usages = message["cpu-usages"]
        self.assertEqual(len(cpu_usages), 0)

        # Trigger a second plugin run, changing the stat file
        plugin._stat_file = thefile2
        self.reactor.advance(interval)

        message2 = plugin.create_message()
        cpu_usages2 = message2["cpu-usages"]
        self.assertNotEqual(cpu_usages, cpu_usages2)
        self.assertEqual([(60, 1.0)], cpu_usages2)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty
        C{cpu-usages} list when no previous data is available.  If an empty
        message is created during exchange, it should not be queued.
        """
        self.mstore.set_accepted_types(["cpu-usage"])

        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.monitor.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    def test_exchange_messages(self):
        """
        The CPU usage plugin queues message when manager.exchange()
        is called.
        """
        contents1 = """cpu  100 100 100 100 100 100 100 0 0 0"""
        contents2 = """cpu  200 100 100 100 100 100 100 0 0 0"""

        thefile, thefile2 = self._write_2_stat_files(contents1, contents2)

        interval = 30
        self.mstore.set_accepted_types(["cpu-usage"])

        plugin = CPUUsage(create_time=self.reactor.time,
                          interval=interval)
        plugin._stat_file = thefile
        self.monitor.add(plugin)

        self.reactor.advance(interval)
        plugin._stat_file = thefile2

        self.reactor.advance(interval)
        self.monitor.exchange()

        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "cpu-usage",
                              "cpu-usages": [(60, 1.0)]}])

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        interval = 30

        plugin = CPUUsage(create_time=self.reactor.time,
                          interval=interval)

        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size * 2)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["cpu-usage"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])
