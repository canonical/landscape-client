import mock

from landscape.client.monitor.memoryinfo import MemoryInfo
from landscape.client.tests.helpers import LandscapeTest, MonitorHelper


class MemoryInfoTest(LandscapeTest):

    helpers = [MonitorHelper]

    SAMPLE_DATA = """
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

    def setUp(self):
        super(MemoryInfoTest, self).setUp()

    def test_read_proc_meminfo(self):
        """
        When the memory info plugin runs it reads data from
        /proc/meminfo which it parses and accumulates to read values.
        This test ensures that /proc/meminfo is always parseable and
        that messages are in the expected format and contain data with
        expected datatypes.
        """
        plugin = MemoryInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size)

        message = plugin.create_message()
        self.assertTrue("type" in message)
        self.assertEqual(message["type"], "memory-info")
        self.assertTrue("memory-info" in message)
        memory_info = message["memory-info"]
        self.assertEqual(len(memory_info), 1)
        self.assertTrue(isinstance(memory_info[0], tuple))
        self.assertTrue(len(memory_info), 3)
        self.assertTrue(isinstance(memory_info[0][0], int))
        self.assertTrue(isinstance(memory_info[0][1], int))
        self.assertTrue(isinstance(memory_info[0][2], int))

    def test_read_sample_data(self):
        """
        This test uses sample /proc/meminfo data and ensures that
        messages contain expected free memory and free swap values.
        """
        filename = self.makeFile(self.SAMPLE_DATA)
        plugin = MemoryInfo(source_filename=filename,
                            create_time=self.reactor.time)
        step_size = self.monitor.step_size
        self.monitor.add(plugin)

        self.reactor.advance(step_size)

        message = plugin.create_message()
        self.assertEqual(message["memory-info"][0], (step_size, 852, 1567))

    def test_messaging_flushes(self):
        """
        Duplicate message should never be created.  If no data is
        available, a message with an empty C{memory-info} list is
        expected.
        """
        filename = self.makeFile(self.SAMPLE_DATA)
        plugin = MemoryInfo(source_filename=filename,
                            create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size)

        message = plugin.create_message()
        self.assertEqual(len(message["memory-info"]), 1)

        message = plugin.create_message()
        self.assertEqual(len(message["memory-info"]), 0)

    def test_ranges_remain_contiguous_after_flush(self):
        """
        The memory info plugin uses the accumulate function to queue
        messages.  Timestamps should always be contiguous, and always
        fall on a step boundary.
        """
        filename = self.makeFile(self.SAMPLE_DATA)
        plugin = MemoryInfo(source_filename=filename,
                            create_time=self.reactor.time)
        self.monitor.add(plugin)

        step_size = self.monitor.step_size
        for i in range(1, 10):
            self.reactor.advance(step_size)
            message = plugin.create_message()
            memory_info = message["memory-info"]
            self.assertEqual(len(memory_info), 1)
            self.assertEqual(memory_info[0][0], step_size * i)

    def test_never_exchange_empty_messages(self):
        """
        The plugin will create a message with an empty C{memory-info}
        list when no data is available.  If an empty message is
        created during exchange, it should not be queued.
        """
        self.mstore.set_accepted_types(["memory-info"])

        filename = self.makeFile(self.SAMPLE_DATA)
        plugin = MemoryInfo(source_filename=filename,
                            create_time=self.reactor.time)
        self.monitor.add(plugin)
        self.monitor.exchange()
        self.assertEqual(len(self.mstore.get_pending_messages()), 0)

    def test_exchange_messages(self):
        """
        The memory info plugin queues messages when manager.exchange()
        is called.  Each message should be aligned to a step boundary;
        messages collected between exchange period should be delivered
        in a single message.
        """
        self.mstore.set_accepted_types(["memory-info"])

        filename = self.makeFile(self.SAMPLE_DATA)
        plugin = MemoryInfo(source_filename=filename,
                            create_time=self.reactor.time)
        step_size = self.monitor.step_size
        self.monitor.add(plugin)

        self.reactor.advance(step_size * 2)
        self.monitor.exchange()

        self.assertMessages(self.mstore.get_pending_messages(),
                            [{"type": "memory-info",
                              "memory-info": [(step_size, 852, 1567),
                                              (step_size * 2, 852, 1567)]}])

    def test_call_on_accepted(self):
        plugin = MemoryInfo(source_filename=self.makeFile(self.SAMPLE_DATA),
                            create_time=self.reactor.time)
        self.monitor.add(plugin)

        self.reactor.advance(self.monitor.step_size * 1)

        with mock.patch.object(self.remote, "send_message"):
            self.reactor.fire(("message-type-acceptance-changed",
                               "memory-info"), True)
            self.remote.send_message.assert_called_once_with(
                mock.ANY, mock.ANY, urgent=True)

    def test_no_message_if_not_accepted(self):
        """
        Don't add any messages at all if the broker isn't currently
        accepting their type.
        """
        plugin = MemoryInfo(create_time=self.reactor.time)
        self.monitor.add(plugin)
        self.reactor.advance(self.monitor.step_size)
        self.monitor.exchange()

        self.mstore.set_accepted_types(["memory-info"])
        self.assertMessages(list(self.mstore.get_pending_messages()), [])
