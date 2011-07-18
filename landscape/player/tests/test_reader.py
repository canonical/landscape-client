from landscape.broker.transport import PayloadRecorder
from landscape.player.reader import PayloadReader
from landscape.tests.helpers import LandscapeTest


class PayloadReaderTest(LandscapeTest):

    def test_load_returns_filename(self):
        """
        Each server exchange is saved in a file with the filename being the
        offset in seconds since recording started.  C{PayloadPlayer.load()}
        should return the filename in addition to the file contents.
        """
        path = self.makeDir()
        recorder = PayloadRecorder(path)

        def static_filename():
            return "filename"
        recorder.get_payload_filename = static_filename
        recorder.save("payload data")

        reader = PayloadReader(path)
        payloads = reader.load()

        self.assertEqual("filename", payloads[0][0])
        self.assertEqual("payload data", payloads[0][1])

    def test_load_returns_multiple_files(self):
        """
        Multiple exchanges should be handled in the same manner as
        a single server exchange.
        """
        path = self.makeDir()
        recorder = PayloadRecorder(path)
        recorder.save("payload data")
        recorder.save("other data")

        reader = PayloadReader(path)
        payloads = reader.load()

        self.assertEqual("payload data", payloads[0][1])
        self.assertEqual("other data", payloads[1][1])
