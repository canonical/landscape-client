

class PayloadPlayer(object):
    def __init__(self, reader, exchange, playback_speed):
        self._exchange = exchange
        self._reader = reader
        self._data = []
        self._playback_speed = playback_speed

    def load(self):
        self._data = self._reader.load()

    def play(self):
        offset = 0
        for offset_str, payload in self._data:
            offset = float(offset_str) / self._playback_speed
            self._exchange.send_at(payload, offset)
        return offset
