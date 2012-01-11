import select
import subprocess
import os


class ObservableRegistration(object):

    def __init__(self, idle_f=None):
        self._notification_observers = []
        self._error_observers = []
        self._succeed_observers = []
        self._fail_observers = []
        self._idle_f = idle_f

    def do_idle(self):
        if self._idle_f:
            self._idle_f()

    def notify_observers(self, message, end="\n", error=False):
        for fun in self._notification_observers:
            fun(message, error)
            self.do_idle()

    def error_observers(self, error_list):
        for fun in self._error_observers:
            fun(error_list)
            self.do_idle()

    def register_notification_observer(self, fun):
        self._notification_observers.append(fun)

    def register_error_observer(self, fun):
        self._error_observers.append(fun)

    def register_succeed_observer(self, fun):
        self._succeed_observers.append(fun)

    def register_fail_observer(self, fun):
        self._fail_observers.append(fun)

    def succeed(self):
        for fun in self._succeed_observers:
            fun()
            self.do_idle()

    def fail(self, error=None):
        for fun in self._fail_observers:
            fun(error=error)
            self.do_idle()

    def register(self, config):
        self.notify_observers("Trying to register ...\n")
        cmd = ["landscape-config", "--silent", "-c",
               os.path.abspath(config.get_config_filename())]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        return_code = None
        while return_code is None:
            readables, w, x = select.select([process.stdout, process.stderr],
                                            [], [], 0)
            for readable in readables:
                message = readable.readline()
                if readable is process.stdout:
                    self.notify_observers(message)
                else:
                    self.error_observers(message)
                self.do_idle()
            return_code = process.poll()
            self.do_idle()
        if return_code == 0:
            self.succeed()
            return True
        else:
            self.fail("Failed with code %s" % str(return_code))
            return False
