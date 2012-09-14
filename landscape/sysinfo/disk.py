from __future__ import division

import os

from twisted.internet.defer import succeed

from landscape.lib.disk import (get_mount_info, get_filesystem_for_path)


def format_megabytes(megabytes):
    if megabytes >= 1024 * 1024:
        return "%.2fTB" % (megabytes / (1024 * 1024))
    elif megabytes >= 1024:
        return "%.2fGB" % (megabytes / 1024)
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
        if main_info is not None:
            total = main_info["total-space"]
            if total <= 0:
                root_main_info = get_filesystem_for_path(
                    "/", self._mounts_file, self._statvfs)
                if root_main_info is not None:
                    total = root_main_info["total-space"]
                    main_info = root_main_info
            if total <= 0:
                main_usage = "unknown"
            else:
                main_usage = usage(main_info)
            self._sysinfo.add_header("Usage of " + main_info["mount-point"],
                                     main_usage)
        else:
            self._sysinfo.add_header("Usage of /home", "unknown")

        seen_mounts = set()
        seen_devices = set()
        infos = list(get_mount_info(self._mounts_file, self._statvfs))
        infos.sort(key=lambda i: len(i["mount-point"]))
        for info in infos:
            total = info["total-space"]
            mount_seen = info["mount-point"] in seen_mounts
            device_seen = info["device"] in seen_devices
            seen_mounts.add(info["mount-point"])
            seen_devices.add(info["device"])
            if mount_seen or device_seen:
                continue

            if total <= 0:
                # Some "virtual" filesystems have 0 total space. ignore them.
                continue

            used = ((total - info["free-space"]) / total) * 100
            if used >= 85:
                self._sysinfo.add_note("%s is using %s"
                                       % (info["mount-point"], usage(info)))
        return succeed(None)
