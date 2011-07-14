from landscape.lib import bpickle


class PayloadPlayer(object):
    """A player that replays old messages.

    @param reader - A L{PayloadReader} that fetches exchanges from the
        filesystem.
    @param exchange - The L{MessageExchange} that messages will be played back
        to.
    @param playback_speed - The speed multiplier at which to play back messages
        at.
    """
    def __init__(self, reader, exchange, playback_speed):
        self._exchange = exchange
        self._reader = reader
        self._data = []
        self._playback_speed = playback_speed

    def load(self):
        """Retrieve exchanges from the L{PayloadReader} and sort them."""
        data = self._reader.load()
        self._data = sorted(data, key=lambda x: float(x[0]))

    def play(self):
        """
        Schedule events with the L{MessageExchange} that will replay the
        messages at the expected time offset.
        """
        for offset_str, payload in self._data:
            offset = float(offset_str) / self._playback_speed
            exchange = bpickle.loads(payload)
            if (len(exchange['messages']) > 0):
                self._exchange.send_at(offset, exchange['messages'])
