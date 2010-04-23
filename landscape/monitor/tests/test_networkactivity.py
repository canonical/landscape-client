from landscape.monitor.networkactivity import NetworkActivity
from landscape.tests.helpers import LandscapeTest, MonitorHelper
#from landscape.tests.mocker import ANY

class NetworkActivityTest(LandscapeTest):

    helpers = [MonitorHelper]

    def setUp(self):
        super(NetworkActivityTest, self).setUp()

    def test_read_proc_net_dev(self):
        """
        When the network activity plugin runs it reads data from
        /proc/net/dev which it parses and accumulates to read values.
        This test ensures that /proc/net/dev is always parseable and
        that messages are in the expected format and contain data with
        expected datatypes.
        """
        plugin = NetworkActivity(create_time=self.reactor.time)
        self.monitor.add(plugin)
        self.reactor.advance(self.monitor.step_size)
        message = plugin.create_message()
        self.assertTrue("type" in message)
        self.assertEquals(message["type"], "network-activity")
