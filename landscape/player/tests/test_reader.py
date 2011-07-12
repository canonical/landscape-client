from landscape.broker.transport import PayloadRecorder
from landscape.player.reader import PayloadReader
from landscape.tests.helpers import LandscapeTest


class PayloadReaderTest(LandscapeTest):

    def test_load_returns_filename(self):
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
        path = self.makeDir()
        recorder = PayloadRecorder(path)
        recorder.save("payload data")
        recorder.save("other data")

        reader = PayloadReader(path)
        payloads = reader.load()

        self.assertEqual("payload data", payloads[0][1])
        self.assertEqual("other data", payloads[1][1])
