from landscape.client.monitor.cpuusage import CPUUsage, LAST_MESURE_KEY
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class CPUUsagePluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def _write_stat_file(self, contents):
        statfile = self.makeFile()
        with open(statfile, "w") as f:
            f.write(contents)
        return statfile

    def test_get_cpu_usage_file_unreadable(self):
        """
        When the file is unreadable or somehow creates an IOError (like when
        it doesn't exist), the method returns None.
        """
        self.log_helper.ignore_errors("Could not open.*")
        thefile = "/tmp/whatever/I/do/not/exist"
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertIs(None, result)

    def test_get_cpu_usage_file_not_changed(self):
        """
        When the stat file did not change between calls, the
        C{_get_cpu_usage} method returns None.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0"

        thefile = self._write_stat_file(contents1)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous measure
        # yet.
        self.assertIs(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertIs(None, result)

    def test_get_cpu_usage_multiline_files(self):
        """
        The C{_get_cpu_usage} method parses multiline stat files correctly.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0\nsome garbage"

        thefile = self._write_stat_file(contents1)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous measure
        # yet.
        self.assertIs(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertIs(None, result)

    def test_get_cpu_usage_100_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        100%, the method returns 1.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0"
        contents2 = "cpu  200 100 100 100 100 100 100 0 0 0"

        thefile = self._write_stat_file(contents1)
        thefile2 = self._write_stat_file(contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous measure
        # yet.
        self.assertIs(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 1)

    def test_get_cpu_usage_0_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        0% (all the changes are in the idle column) the method returns 0.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0"
        contents2 = "cpu  100 100 100 200 100 100 100 0 0 0"

        thefile = self._write_stat_file(contents1)
        thefile2 = self._write_stat_file(contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous measure
        # yet.
        self.assertIs(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 0)

    def test_get_cpu_usage_50_percent_usage(self):
        """
        When two consecutive calls to C{_get_cpu_usage} show a CPU usage of
        50% (as much changed in an "active" column that in the idle column)
        the method returns 0.5.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0"
        contents2 = "cpu  200 100 100 200 100 100 100 0 0 0"

        thefile = self._write_stat_file(contents1)
        thefile2 = self._write_stat_file(contents2)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        result = plugin._get_cpu_usage(stat_file=thefile)
        # The first run will return None since we don't have a previous measure
        # yet.
        self.assertIs(None, result)

        result = plugin._get_cpu_usage(stat_file=thefile2)
        self.assertEqual(result, 0.5)

    def test_get_cpu_usage_after_reboot(self):
        """
        When the computer just rebooted, we might have a case where the
        previous values are larger that the current values (since the kernel
        counts quantums allocated since boot). In this case, the method should
        return None.
        """
        contents1 = "cpu  100 100 100 100 100 100 100 0 0 0"

        measure1 = (700, 100)
        measure2 = (900, 10)

        thefile = self._write_stat_file(contents1)
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)
        plugin._persist.set(LAST_MESURE_KEY, measure2)

        result = plugin._get_cpu_usage(stat_file=thefile)
        self.assertIs(None, result)
        self.assertEqual(measure1, plugin._persist.get(LAST_MESURE_KEY))

    def test_create_message(self):
        """
        Calling create_message returns an expected message.
        """
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        plugin._cpu_usage_points = []
        message = plugin.create_message()
        self.assertIn("type", message)
        self.assertEqual(message["type"], "cpu-usage")
        self.assertIn("cpu-usages", message)
        cpu_usages = message["cpu-usages"]
        self.assertEqual(len(cpu_usages), 0)

        point = (60, 1.0)
        plugin._cpu_usage_points = [point]
        message = plugin.create_message()
        self.assertIn("type", message)
        self.assertEqual(message["type"], "cpu-usage")
        self.assertIn("cpu-usages", message)
        cpu_usages = message["cpu-usages"]
        self.assertEqual(len(cpu_usages), 1)
        self.assertEqual(point, cpu_usages[0])

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
        self.mstore.set_accepted_types(["cpu-usage"])

        plugin = CPUUsage(create_time=self.reactor.time)
        plugin._cpu_usage_points = [(60, 1.0)]
        self.monitor.add(plugin)

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

    def test_plugin_run(self):
        """
        The plugin's run() method fills in the _cpu_usage_points with
        accumulated samples after each C{monitor.step_size} period.
        """
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        def fake_get_cpu_usage(self):
            return 1.0

        plugin._get_cpu_usage = fake_get_cpu_usage
        self.reactor.advance(self.monitor.step_size * 2)

        self.assertNotEqual([], plugin._cpu_usage_points)
        self.assertEqual([(300, 1.0), (600, 1.0)], plugin._cpu_usage_points)

    def test_plugin_run_with_None(self):
        """
        The plugin's run() method fills in the _cpu_usage_points with
        accumulated samples after each C{monitor.step_size} period.
        Holes in the data (in case of error the method returns None) are
        handled gracefully, and are filled with averaged data.
        """
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        def fake_get_cpu_usage(self):
            return 1.0

        def fake_get_cpu_usage_none(self):
            return None

        plugin._get_cpu_usage = fake_get_cpu_usage
        self.reactor.advance(self.monitor.step_size)
        plugin._get_cpu_usage = fake_get_cpu_usage_none
        self.reactor.advance(self.monitor.step_size)

        self.assertNotEqual([], plugin._cpu_usage_points)
        self.assertEqual([(300, 1.0)], plugin._cpu_usage_points)

        # If we record values once again the "blank" period will be smoothed
        # over with the new points.
        plugin._get_cpu_usage = fake_get_cpu_usage
        self.reactor.advance(self.monitor.step_size)
        self.assertEqual([(300, 1.0), (600, 1.0), (900, 1.0)],
                         plugin._cpu_usage_points)
