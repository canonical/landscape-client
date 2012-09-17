from __future__ import division

import os
import statvfs


# List of filesystem types authorized when generating disk use statistics.
STABLE_FILESYSTEMS = frozenset(
    ["ext", "ext2", "ext3", "ext4", "reiserfs", "ntfs", "msdos", "dos", "vfat",
     "xfs", "hpfs", "jfs", "ufs", "hfs", "hfsplus"])


def get_mount_info(mounts_file, statvfs_,
                   filesystems_whitelist=STABLE_FILESYSTEMS):
    """
    This is a generator that yields information about mounted filesystems.

    @param mounts_file: A file with information about mounted filesystems,
        such as C{/proc/mounts}.
    @param statvfs_: A function to get file status information.
    @param filesystems_whitelist: Optionally, a list of which filesystems to
        stat.
    @return: A C{dict} with C{device}, C{mount-point}, C{filesystem},
        C{total-space} and C{free-space} keys. If the filesystem information
        is not available, C{None} is returned. Both C{total-space} and
        C{free-space} are in megabytes.
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


def get_filesystem_for_path(path, mounts_file, statvfs_):
    """
    Tries to determine to which of the mounted filesystem C{path} belongs to,
    and then returns information about that filesystem or C{None} if it
    couldn't be determined.

    @param path: The path we want filesystem information about.
    @param mounts_file: A file with information about mounted filesystems,
        such as C{/proc/mounts}.
    @param statvfs_: A function to get file status information.
    @param filesystems_whitelist: Optionally, a list of which filesystems to
        stat.
    @return: A C{dict} with C{device}, C{mount-point}, C{filesystem},
        C{total-space} and C{free-space} keys. If the filesystem information
        is not available, C{None} is returned. Both C{total-space} and
        C{free-space} are in megabytes.
    """
    candidate = None
    path = os.path.realpath(path)
    path_segments = path.split("/")
    for info in get_mount_info(mounts_file, statvfs_):
        mount_segments = info["mount-point"].split("/")
        if path.startswith(info["mount-point"]):
            if ((not candidate)
                or path_segments[:len(mount_segments)] == mount_segments):
                candidate = info
    return candidate
