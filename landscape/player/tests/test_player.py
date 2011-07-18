from landscape.lib import bpickle
from landscape.player.player import PayloadPlayer
from landscape.tests.helpers import LandscapeTest


class PayloadReaderTest(LandscapeTest):

    def test_load_calls_reader(self):
        """Exchanges should be loaded from C{PayloadPlayer}."""
        calls = []

        class Reader(object):
            def __init__(self, calls):
                self.calls = calls

            def load(self):
                self.calls.append(True)
                return []

        player = PayloadPlayer(Reader(calls), None, 1)
        player.load()
        self.assertTrue(calls[0])

    def test_load_orders_data(self):
        """Exchanges should be ordered according to time offset."""

        class Reader(object):

            def load(self):
                return [
                    ("55.55", bpickle.dumps({"type": "message type"})),
                    ("6.66", bpickle.dumps({"type": "message type 2"})),
                ]

        player = PayloadPlayer(Reader(), None, 1)
        player.load()
        self.assertEqual("6.66", player._data[0][0])

    def test_play_should_schedule_exchanges(self):
        """
        Exchanges with messages should be scheduled for delivery.
        """
        calls = []

        class Exchange(object):

            def __init__(self, calls):
                self.calls = calls

            def send_at(self, offset, messages):
                self.calls.append((offset, messages))

        player = PayloadPlayer(None, Exchange(calls), 1)
        player._data = [("6", bpickle.dumps({"messages": ["in a bottle"]}))]
        player.play()

        self.assertEqual(6, int(calls[0][0]))
        self.assertEqual(["in a bottle"], calls[0][1])
