from __future__ import division

import os
import statvfs


def get_mount_info(mounts_file, statvfs_, filesystems_whitelist=None):
    """
    Given a mounts file (e.g., /proc/mounts), generate dicts with the following
    keys:

    @param filesystems_whitelist: if provided, the list of file systems which
        we're allowed to stat.

     - device: The device file which is mounted.
     - mount-point: The path at which the filesystem is mounted.
     - filesystem: The filesystem type.
     - total-space: The capacity of the filesystem in megabytes.
     - free-space: The amount of space available in megabytes.
    """
    for line in open(mounts_file):
        try:
            device, mount_point, filesystem = line.split()[:3]
            mount_point = mount_point.decode("string-escape")
        except ValueError:
            continue
        if (filesystems_whitelist is not None and
            filesystem not in filesystems_whitelist):
            continue
        megabytes = 1024 * 1024
        try:
            stats = statvfs_(mount_point)
        except OSError:
            continue
        block_size = stats[statvfs.F_BSIZE]
        total_space = (stats[statvfs.F_BLOCKS] * block_size) // megabytes
        free_space = (stats[statvfs.F_BFREE] * block_size) // megabytes
        yield {"device": device, "mount-point": mount_point,
               "filesystem": filesystem, "total-space": total_space,
               "free-space": free_space}


def get_filesystem_for_path(path, mounts_file, statvfs_,
                            filesystems_whitelist=None):
    candidate = None
    path = os.path.realpath(path)
    path_segments = path.split("/")
    for info in get_mount_info(mounts_file, statvfs_, filesystems_whitelist):
        mount_segments = info["mount-point"].split("/")
        if path.startswith(info["mount-point"]):
            if ((not candidate)
                or path_segments[:len(mount_segments)] == mount_segments):
                candidate = info
    return candidate
