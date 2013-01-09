from landscape.monitor.cpuusage import CPUUsage
from landscape.tests.helpers import LandscapeTest, MonitorHelper

class CPUUsagePluginTest(LandscapeTest):

    helpers = [MonitorHelper]

    def test_real_cpu_usage(self):
        """
        """
        plugin = CPUUsage(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size)

        message = plugin.create_message()
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "cpu-usage")
        self.assertTrue("cpu-usage" in message)

        cpu_usages = message["cpu-usage"]
        self.assertEqual(len(cpu_usages), 1)
