from __future__ import division

import os

from twisted.internet.defer import succeed

from landscape.lib.disk import get_mount_info, get_filesystem_for_path


def format_megabytes(megabytes):
    if megabytes >= 1024*1024:
        return "%.2fTB" % (megabytes/(1024*1024))
    elif megabytes >= 1024:
        return "%.2fGB" % (megabytes/1024)
    else:
        return "%dMB" % (megabytes)


def percent(used, total):
    return "%0.1f%%" % ((used / total) * 100)


class Disk(object):

    def __init__(self, mounts_file="/proc/mounts", statvfs=os.statvfs):
        self._mounts_file = mounts_file
        self._statvfs = statvfs

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        main_filesystem = get_filesystem_for_path("/home", self._mounts_file,
                                                  self._statvfs)
        self._sysinfo.add_header("Usage of " + main_filesystem["mount-point"],
                                 percent(main_filesystem["total-space"] - main_filesystem["free-space"],
                                         main_filesystem["total-space"]))
        for info in get_mount_info(self._mounts_file, self._statvfs):
            if info["filesystem"] in ("udf", "iso9660"):
                continue
            total = info["total-space"]
            if total > 0:
                used = ((total - info["free-space"]) / total) * 100
            else:
                # Some "virtual" filesystems have 0 total space. ignore them.
                used = 0
            if used >= 85:
                self._sysinfo.add_note("%s is using %0.1f%% of %s"
                                       % (info["mount-point"], used,
                                          format_megabytes(total)))
        return succeed(None)
