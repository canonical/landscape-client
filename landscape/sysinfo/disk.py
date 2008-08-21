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


def usage(info):
    total = info["total-space"]
    used = total - info["free-space"]
    return "%0.1f%% of %s" % ((used / total) * 100, format_megabytes(total))

class Disk(object):

    def __init__(self, mounts_file="/proc/mounts", statvfs=os.statvfs):
        self._mounts_file = mounts_file
        self._statvfs = statvfs

    def register(self, sysinfo):
        self._sysinfo = sysinfo

    def run(self):
        main_info = get_filesystem_for_path("/home", self._mounts_file,
                                                  self._statvfs)
        total = main_info["total-space"]
        self._sysinfo.add_header("Usage of " + main_info["mount-point"],
                                 usage(main_info))

        for info in get_mount_info(self._mounts_file, self._statvfs):
            total = info["total-space"]

            if info["filesystem"] in ("udf", "iso9660"):
                continue
            if total <= 0:
                # Some "virtual" filesystems have 0 total space. ignore them.
                continue

            used = ((total - info["free-space"]) / total) * 100
            if used >= 85:
                self._sysinfo.add_note("%s is using %s"
                                       % (info["mount-point"], usage(info)))
        return succeed(None)
