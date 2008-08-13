from __future__ import division

import os

from twisted.internet.defer import succeed

from landscape.monitor.mountinfo import MountInfo


class Disk(object):

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        mi = MountInfo()
        for info in mi._get_mount_info():
            total, free = mi._get_space(info["mount-point"])
            used = (total - free) / total
            self._sysinfo.add_note("%s is using %0.0f%% of %s"
                                   % (info["mount-point"], used*100, total))
        return succeed(None)
