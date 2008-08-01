from twisted.internet.defer import succeed


current_instance = None


class TestPlugin(object):

    def __init__(self):
        self.sysinfo = None
        self.has_run = False

        global current_instance
        current_instance = self

    def register(self, sysinfo):
        self.sysinfo = sysinfo

    def run(self):
        self.has_run = True
        self.sysinfo.add_header("Test header", "Test value")
        self.sysinfo.add_note("Test note")
        self.sysinfo.add_footnote("Test footnote")
        return succeed(None)
