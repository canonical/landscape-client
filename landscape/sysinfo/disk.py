from __future__ import division

import os

from twisted.internet.defer import succeed

from landscape.monitor.mountinfo import MountInfo


def format_megabytes(megabytes):
    if megabytes >= 1024*1024:
        return "%.2fTB" % (megabytes/(1024*1024))
    elif megabytes >= 1024:
        return "%.2fGB" % (megabytes/1024)
    else:
        return "%dMB" % (megabytes)


class Disk(object):

    def __init__(self, mounts_file="/proc/mounts", statvfs=os.statvfs):
        self._mounts_file = mounts_file
        self._statvfs = statvfs

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        mi = MountInfo(mounts_file=self._mounts_file, statvfs=self._statvfs)
        for info in mi._get_mount_info():
            total, free = mi._get_space(info["mount-point"])
            used = ((total - free) / total) * 100
            if used >= 85:
                self._sysinfo.add_note("%s is using %0.1f%% of %s"
                                       % (info["mount-point"], used,
                                          format_megabytes(total)))
        return succeed(None)
