import os
from datetime import datetime
from dateutil import parser
from unittest import TestCase
from unittest.mock import patch
from subprocess import run as run_orig

from landscape.lib import testing

# from landscape.lib.security import get_listeningports
from landscape.lib.security import (
    RKHunterLogReader,
    RKHunterLiveInfo,
    RKHunterInfo,
    rkhunter_cmd,
)

COMMON_VERSION = "8.4.3"
COMMON_DATETIME = parser.parse("28 apr 2028 17:44:03 CET")

SAMPLE_RKHUNTER_VERSION = """Rootkit Hunter 8.4.3

This software was developed by the Rootkit Hunter project team.
Please review your rkhunter configuration files before using.
Please review the documentation before posting bug reports or questions.
To report bugs, provide patches or comments, please go to:
http://rkhunter.sourceforge.net

To ask questions about rkhunter, please use the rkhunter-users mailing list.
Note this is a moderated list: please subscribe before posting.

Rootkit Hunter comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under the
terms of the GNU General Public License. See the LICENSE file for details.

"""

SAMPLE_RKHUNTER_LOG_1 = """[17:44:00]
[17:44:00] System checks summary
[17:44:00] =====================
[17:44:00]
[17:44:00] File properties checks...
[17:44:00] Files checked: 145
[17:44:00] Suspect files: 0
[17:44:00]
[17:44:00] Rootkit checks...
[17:44:00] Rootkits checked : 478
[17:44:00] Possible rootkits: 1
[17:44:00rkhunter_info_log
[17:44:00] Applications checks...
[17:44:00] All checks skipped
[17:44:00]
[17:44:00] The system checks took: 2 minutes and 36 seconds
[17:44:00]
[17:44:00] Info: End date is fri 28 apr 2028 17:44:03 CET"""


SAMPLE_RKHUNTER_LOG_2 = """[17:44:00]
[17:44:00] System checks summary
[17:44:00] =====================
[17:44:00]
[17:44:00] File properties checks...
[17:44:00] Files checked: 145
[17:44:00] Suspect files: 48
[17:44:00]
[17:44:00] Rootkit checks...
[17:44:00] Rootkits checked : 478
[17:44:00] Possible rootkits: 1
[17:44:00rkhunter_info_log
[17:44:00] Applications checks...
[17:44:00] All checks skipped
[17:44:00]
[17:44:00] The system checks took: 2 minutes and 36 seconds
[17:44:00]
[17:44:00] Info: End date is fri 28 apr 2028 17:44:03 CET"""


SAMPLE_RKHUNTER_LOG_PARTIAL_1 = """[17:44:00]
[17:44:00] System checks summary
[17:44:00] =====================
[17:44:00]
[17:44:00] File properties checks...
[17:44:00] Files checked: 145
[17:44:00] Suspect files: 0
[17:44:00]
[17:44:00] Rootkit checks...
[17:44:00] Rootkits checked : 478
[17:44:00] Possible rootkits: 1
[17:44:00rkhunter_info_log
[17:44:00] Applications checks...
[17:44:00] All checks skipped
[17:44:00]
[17:44:00] The system checks took: 2 minutes and 36 seconds
[17:44:00]"""

SAMPLE_RKHUNTER_LOG_PARTIAL_2 = """[17:44:00]
[17:44:00] Rootkit checks...
[17:44:00] Rootkits checked : 478
[17:44:00] Possible rootkits: 1
[17:44:00rkhunter_info_log
[17:44:00] Applications checks...
[17:44:00] All checks skipped
[17:44:00]
[17:44:00] The system checks took: 2 minutes and 36 seconds
[17:44:00]
[17:44:00] Info: End date is fri 28 apr 2028 17:44:03 CET"""

SAMPLE_RKHUNTER_EXECUTION_OUTPUT = """[ Rootkit Hunter version 1.4.6 ]

Checking system commands...

  Performing 'strings' command checks
    Checking 'strings' command                               [ OK ]

  Performing 'shared libraries' checks
    Checking for preloading variables                        [ None found ]
    Checking for preloaded libraries                         [ None found ]
    Checking LD_LIBRARY_PATH variable                        [ Not found ]

  Performing file properties checks
    Checking for prerequisites                               [ OK ]
    /usr/sbin/adduser                                        [ OK ]
    /usr/sbin/chroot                                         [ OK ]
    /usr/sbin/cron                                           [ OK ]
    /usr/sbin/depmod                                         [ OK ]
    /usr/sbin/fsck                                           [ OK ]
    /usr/sbin/groupadd                                       [ OK ]
    /usr/sbin/groupdel                                       [ OK ]
    /usr/sbin/groupmod                                       [ OK ]
    /usr/sbin/grpck                                          [ OK ]
    /usr/sbin/ifconfig                                       [ OK ]
    /usr/sbin/init                                           [ OK ]
    /usr/sbin/insmod                                         [ OK ]
    /usr/sbin/ip                                             [ OK ]
    /usr/sbin/lsmod                                          [ OK ]
    /usr/sbin/modinfo                                        [ OK ]
    /usr/sbin/modprobe                                       [ OK ]
    /usr/sbin/nologin                                        [ OK ]
    /usr/sbin/pwck                                           [ OK ]
    /usr/sbin/rmmod                                          [ OK ]
    /usr/sbin/route                                          [ OK ]
    /usr/sbin/rsyslogd                                       [ OK ]
    /usr/sbin/runlevel                                       [ OK ]
    /usr/sbin/sulogin                                        [ OK ]
    /usr/sbin/sysctl                                         [ OK ]
    /usr/sbin/useradd                                        [ OK ]
    /usr/sbin/userdel                                        [ OK ]
    /usr/sbin/usermod                                        [ OK ]
    /usr/sbin/vipw                                           [ OK ]
    /usr/sbin/unhide                                         [ OK ]
    /usr/sbin/unhide-linux                                   [ OK ]
    /usr/sbin/unhide-posix                                   [ OK ]
    /usr/sbin/unhide-tcp                                     [ OK ]
    /usr/bin/awk                                             [ OK ]
    /usr/bin/basename                                        [ OK ]
    /usr/bin/bash                                            [ OK ]
    /usr/bin/cat                                             [ OK ]
    /usr/bin/chattr                                          [ OK ]
    /usr/bin/chmod                                           [ OK ]
    /usr/bin/chown                                           [ OK ]
    /usr/bin/cp                                              [ OK ]
    /usr/bin/curl                                            [ Warning ]
br0th3r@carmen:~/zonaprog/src/canonical/security$ cat rkhunter.output
[ Rootkit Hunter version 1.4.6 ]

Checking system commands...

  Performing 'strings' command checks
    Checking 'strings' command                               [ OK ]

  Performing 'shared libraries' checks
    Checking for preloading variables                        [ None found ]
    Checking for preloaded libraries                         [ None found ]
    Checking LD_LIBRARY_PATH variable                        [ Not found ]

  Performing file properties checks
    Checking for prerequisites                               [ OK ]
    /usr/sbin/adduser                                        [ OK ]
    /usr/sbin/chroot                                         [ OK ]
    /usr/sbin/cron                                           [ OK ]
    /usr/sbin/depmod                                         [ OK ]
    /usr/sbin/fsck                                           [ OK ]
    /usr/sbin/groupadd                                       [ OK ]
    /usr/sbin/groupdel                                       [ OK ]
    /usr/sbin/groupmod                                       [ OK ]
    /usr/sbin/grpck                                          [ OK ]
    /usr/sbin/ifconfig                                       [ OK ]
    /usr/sbin/init                                           [ OK ]
    /usr/sbin/insmod                                         [ OK ]
    /usr/sbin/ip                                             [ OK ]
    /usr/sbin/lsmod                                          [ OK ]
    /usr/sbin/modinfo                                        [ OK ]
    /usr/sbin/modprobe                                       [ OK ]
    /usr/sbin/nologin                                        [ OK ]
    /usr/sbin/pwck                                           [ OK ]
    /usr/sbin/rmmod                                          [ OK ]
    /usr/sbin/route                                          [ OK ]
    /usr/sbin/rsyslogd                                       [ OK ]
    /usr/sbin/runlevel                                       [ OK ]
    /usr/sbin/sulogin                                        [ OK ]
    /usr/sbin/sysctl                                         [ OK ]
    /usr/sbin/useradd                                        [ OK ]
    /usr/sbin/userdel                                        [ OK ]
    /usr/sbin/usermod                                        [ OK ]
    /usr/sbin/vipw                                           [ OK ]
    /usr/sbin/unhide                                         [ OK ]
    /usr/sbin/unhide-linux                                   [ OK ]
    /usr/sbin/unhide-posix                                   [ OK ]
    /usr/sbin/unhide-tcp                                     [ OK ]
    /usr/bin/awk                                             [ OK ]
    /usr/bin/basename                                        [ OK ]
    /usr/bin/bash                                            [ OK ]
    /usr/bin/cat                                             [ OK ]
    /usr/bin/chattr                                          [ OK ]
    /usr/bin/chmod                                           [ OK ]
    /usr/bin/chown                                           [ OK ]
    /usr/bin/cp                                              [ OK ]
    /usr/bin/curl                                            [ Warning ]
    /usr/bin/cut                                             [ OK ]
    /usr/bin/date                                            [ OK ]
    /usr/bin/df                                              [ OK ]
    /usr/bin/diff                                            [ OK ]
    /usr/bin/dirname                                         [ OK ]
    /usr/bin/dmesg                                           [ OK ]
    /usr/bin/dpkg                                            [ OK ]
    /usr/bin/dpkg-query                                      [ OK ]
    /usr/bin/du                                              [ OK ]
    /usr/bin/echo                                            [ OK ]
    /usr/bin/ed                                              [ OK ]
    /usr/bin/egrep                                           [ OK ]
    /usr/bin/env                                             [ OK ]
    /usr/bin/fgrep                                           [ OK ]
    /usr/bin/file                                            [ OK ]
    /usr/bin/find                                            [ OK ]
    /usr/bin/fuser                                           [ OK ]
    /usr/bin/GET                                             [ OK ]
    /usr/bin/grep                                            [ OK ]
    /usr/bin/groups                                          [ OK ]
    /usr/bin/head                                            [ OK ]
    /usr/bin/id                                              [ OK ]
    /usr/bin/ip                                              [ OK ]
    /usr/bin/ipcs                                            [ OK ]
    /usr/bin/kill                                            [ OK ]
    /usr/bin/killall                                         [ OK ]
    /usr/bin/last                                            [ OK ]
    /usr/bin/lastlog                                         [ OK ]
    /usr/bin/ldd                                             [ OK ]
    /usr/bin/less                                            [ OK ]
    /usr/bin/locate                                          [ OK ]
    /usr/bin/logger                                          [ OK ]
    /usr/bin/login                                           [ OK ]
    /usr/bin/ls                                              [ OK ]
    /usr/bin/lsattr                                          [ OK ]
    /usr/bin/lsmod                                           [ OK ]
    /usr/bin/lsof                                            [ OK ]
    /usr/bin/mail                                            [ OK ]
    /usr/bin/md5sum                                          [ OK ]
    /usr/bin/mktemp                                          [ OK ]
    /usr/bin/more                                            [ OK ]
    /usr/bin/mount                                           [ OK ]
    /usr/bin/mv                                              [ OK ]
    /usr/bin/netstat                                         [ OK ]
    /usr/bin/newgrp                                          [ OK ]
    /usr/bin/passwd                                          [ OK ]
    /usr/bin/perl                                            [ OK ]
    /usr/bin/pgrep                                           [ OK ]
    /usr/bin/ping                                            [ OK ]
    /usr/bin/pkill                                           [ OK ]
    /usr/bin/ps                                              [ OK ]
    /usr/bin/pstree                                          [ OK ]
    /usr/bin/pwd                                             [ OK ]
    /usr/bin/readlink                                        [ OK ]
    /usr/bin/rkhunter                                        [ OK ]
    /usr/bin/runcon                                          [ OK ]
    /usr/bin/sed                                             [ OK ]
    /usr/bin/sh                                              [ OK ]
    /usr/bin/sha1sum                                         [ OK ]
    /usr/bin/sha224sum                                       [ OK ]
    /usr/bin/sha256sum                                       [ OK ]
    /usr/bin/sha384sum                                       [ OK ]
    /usr/bin/sha512sum                                       [ OK ]
    /usr/bin/size                                            [ OK ]
    /usr/bin/sort                                            [ OK ]
    /usr/bin/ssh                                             [ OK ]
    /usr/bin/stat                                            [ OK ]
    /usr/bin/strace                                          [ OK ]
    /usr/bin/strings                                         [ OK ]
    /usr/bin/su                                              [ OK ]
    /usr/bin/sudo                                            [ OK ]
    /usr/bin/tail                                            [ OK ]
    /usr/bin/telnet                                          [ OK ]
    /usr/bin/test                                            [ OK ]
    /usr/bin/top                                             [ OK ]
    /usr/bin/touch                                           [ OK ]
    /usr/bin/tr                                              [ OK ]
    /usr/bin/uname                                           [ OK ]
    /usr/bin/uniq                                            [ OK ]
    /usr/bin/users                                           [ OK ]
    /usr/bin/vmstat                                          [ OK ]
    /usr/bin/w                                               [ OK ]
    /usr/bin/watch                                           [ OK ]
    /usr/bin/wc                                              [ OK ]
    /usr/bin/wget                                            [ OK ]
    /usr/bin/whatis                                          [ OK ]
    /usr/bin/whereis                                         [ OK ]
    /usr/bin/which                                           [ OK ]
    /usr/bin/who                                             [ OK ]
    /usr/bin/whoami                                          [ OK ]
    /usr/bin/numfmt                                          [ OK ]
    /usr/bin/kmod                                            [ OK ]
    /usr/bin/systemd                                         [ OK ]
    /usr/bin/systemctl                                       [ OK ]
    /usr/bin/gawk                                            [ OK ]
    /usr/bin/lwp-request                                     [ OK ]
    /usr/bin/locate.findutils                                [ OK ]
    /usr/bin/bsd-mailx                                       [ OK ]
    /usr/bin/dash                                            [ OK ]
    /usr/bin/x86_64-linux-gnu-size                           [ OK ]
    /usr/bin/x86_64-linux-gnu-strings                        [ OK ]
    /usr/bin/telnet.netkit                                   [ OK ]
    /usr/bin/which.debianutils                               [ OK ]
    /usr/lib/systemd/systemd                                 [ OK ]

Checking for rootkits...

  Performing check of known rootkit files and directories
    55808 Trojan - Variant A                                 [ Not found ]
    ADM Worm                                                 [ Not found ]
    AjaKit Rootkit                                           [ Not found ]
    Adore Rootkit                                            [ Not found ]
    aPa Kit                                                  [ Not found ]
    Apache Worm                                              [ Not found ]
    Ambient (ark) Rootkit                                    [ Not found ]
    Balaur Rootkit                                           [ Not found ]
    BeastKit Rootkit                                         [ Not found ]
    beX2 Rootkit                                             [ Not found ]
    BOBKit Rootkit                                           [ Not found ]
    cb Rootkit                                               [ Not found ]
    CiNIK Worm (Slapper.B variant)                           [ Not found ]
    Danny-Boy's Abuse Kit                                    [ Not found ]
    Devil RootKit                                            [ Not found ]
    Diamorphine LKM                                          [ Not found ]
    Dica-Kit Rootkit                                         [ Not found ]
    Dreams Rootkit                                           [ Not found ]
    Duarawkz Rootkit                                         [ Not found ]
    Ebury backdoor                                           [ Not found ]
    Enye LKM                                                 [ Not found ]
    Flea Linux Rootkit                                       [ Not found ]
    Fu Rootkit                                               [ Not found ]
    Fuck`it Rootkit                                          [ Not found ]
    GasKit Rootkit                                           [ Not found ]
    Heroin LKM                                               [ Not found ]
    HjC Kit                                                  [ Not found ]
    ignoKit Rootkit                                          [ Not found ]
    IntoXonia-NG Rootkit                                     [ Not found ]
    Irix Rootkit                                             [ Not found ]
    Jynx Rootkit                                             [ Not found ]
    Jynx2 Rootkit                                            [ Not found ]
    KBeast Rootkit                                           [ Not found ]
    Kitko Rootkit                                            [ Not found ]
    Knark Rootkit                                            [ Not found ]
    ld-linuxv.so Rootkit                                     [ Not found ]
    Li0n Worm                                                [ Not found ]
    Lockit / LJK2 Rootkit                                    [ Not found ]
    Mokes backdoor                                           [ Not found ]
    Mood-NT Rootkit                                          [ Not found ]
    MRK Rootkit                                              [ Not found ]
    Ni0 Rootkit                                              [ Not found ]
    Ohhara Rootkit                                           [ Not found ]
    Optic Kit (Tux) Worm                                     [ Not found ]
    Oz Rootkit                                               [ Not found ]
    Phalanx Rootkit                                          [ Not found ]
    Phalanx2 Rootkit                                         [ Not found ]
    Phalanx2 Rootkit (extended tests)                        [ Not found ]
    Portacelo Rootkit                                        [ Not found ]
    R3dstorm Toolkit                                         [ Not found ]
    RH-Sharpe's Rootkit                                      [ Not found ]
    RSHA's Rootkit                                           [ Not found ]
    Scalper Worm                                             [ Not found ]
    Sebek LKM                                                [ Not found ]
    Shutdown Rootkit                                         [ Not found ]
    SHV4 Rootkit                                             [ Not found ]
    SHV5 Rootkit                                             [ Not found ]
    Sin Rootkit                                              [ Not found ]
    Slapper Worm                                             [ Not found ]
    Sneakin Rootkit                                          [ Not found ]
    'Spanish' Rootkit                                        [ Not found ]
    Suckit Rootkit                                           [ Not found ]
    Superkit Rootkit                                         [ Not found ]
    TBD (Telnet BackDoor)                                    [ Not found ]
    TeLeKiT Rootkit                                          [ Not found ]
    T0rn Rootkit                                             [ Not found ]
    trNkit Rootkit                                           [ Not found ]
    Trojanit Kit                                             [ Not found ]
    Tuxtendo Rootkit                                         [ Not found ]
    URK Rootkit                                              [ Not found ]
    Vampire Rootkit                                          [ Not found ]
    VcKit Rootkit                                            [ Not found ]
    Volc Rootkit                                             [ Not found ]
    Xzibit Rootkit                                           [ Not found ]
    zaRwT.KiT Rootkit                                        [ Not found ]
    ZK Rootkit                                               [ Not found ]

  Performing additional rootkit checks
    Suckit Rootkit additional checks                         [ OK ]
    Checking for possible rootkit files and directories      [ None found ]
    Checking for possible rootkit strings                    [ None found ]

  Performing malware checks
    Checking running processes for suspicious files          [ None found ]
    Checking for login backdoors                             [ None found ]
    Checking for sniffer log files                           [ None found ]
    Checking for suspicious directories                      [ None found ]
    Checking for suspicious (large) shared memory segments   [ None found ]
    Checking for Apache backdoor                             [ Not found ]

  Performing Linux specific checks
    Checking loaded kernel modules                           [ OK ]
    Checking kernel module names                             [ OK ]

Checking the network...

  Performing checks on the network ports
    Checking for backdoor ports                              [ None found ]

  Performing checks on the network interfaces
    Checking for promiscuous interfaces                      [ None found ]

Checking the local host...

  Performing system boot checks
    Checking for local host name                             [ Found ]
    Checking for system startup files                        [ Found ]
    Checking system startup files for malware                [ None found ]

  Performing group and account checks
    Checking for passwd file                                 [ Found ]
    Checking for root equivalent (UID 0) accounts            [ None found ]
    Checking for passwordless accounts                       [ None found ]
    Checking for passwd file changes                         [ None found ]
    Checking for group file changes                          [ None found ]
    Checking root account shell history files                [ OK ]

  Performing system configuration file checks
    Checking for an SSH configuration file                   [ Not found ]
    Checking for a running system logging daemon             [ Found ]
    Checking for a system logging configuration file         [ Found ]
    Checking if syslog remote logging is allowed             [ Not allowed ]

  Performing filesystem checks
    Checking /dev for suspicious file types                  [ Warning ]
    Checking for hidden files and directories                [ Warning ]


System checks summary
=====================

File properties checks...
    Files checked: 145
    Suspect files: 1

Rootkit checks...
    Rootkits checked : 478
    Possible rootkits: 0

Applications checks...
    All checks skipped

The system checks took: 3 minutes and 34 seconds

All results have been written to the log file: /var/log/rkhunter.log

One or more warnings have been found while checking the system.
Please check the log file (/var/log/rkhunter.log)

"""

echo_cmd = "/usr/bin/echo"


def sample_subprocess_run_scan(
    *args,
    **kwargs,
):
    if args[0][1] == "-c":
        args = ([echo_cmd, "-n", "-e", SAMPLE_RKHUNTER_EXECUTION_OUTPUT],)
    elif args[0][1] == "--version":
        args = ([echo_cmd, "-n", "-e", SAMPLE_RKHUNTER_VERSION],)
    return run_orig(*args, **kwargs)


class BaseTestCase(
    testing.TwistedTestCase,
    testing.FSTestCase,
    TestCase,
):
    @patch("landscape.lib.security.subprocess.run", sample_subprocess_run_scan)
    def test_cmd_version(self):
        rklive = RKHunterLiveInfo()
        self.assertEqual(rklive.get_version(), COMMON_VERSION)


class RKHunterLogTest(BaseTestCase):
    """Test for parsing /var/log/rkhunter.log"""

    def test_read_empty_file(self):
        filename = self.makeFile("")
        rkinfo = RKHunterLogReader(filename)
        self.assertEqual(rkinfo.get_last_log(), None)

    @patch(
        "landscape.lib.security.datetime",
        side_effect=lambda *args, **kw: datetime(*args, **kw),
    )
    @patch("landscape.lib.security.subprocess.run", sample_subprocess_run_scan)
    def test_read_rkhunter_info_log_1(self, mock_datetime):
        mock_datetime.now.return_value = COMMON_DATETIME
        filename = self.makeFile(SAMPLE_RKHUNTER_LOG_1)
        rkinfo = RKHunterLogReader(filename)
        self.assertEqual(
            rkinfo.get_last_log().dict(),
            RKHunterInfo(
                version=COMMON_VERSION,
                files_checked=145,
                files_suspect=0,
                rootkit_checked=478,
                rootkit_suspect=1,
                timestamp=COMMON_DATETIME,
            ).dict(),
        )

    @patch(
        "landscape.lib.security.datetime",
        side_effect=lambda *args, **kw: datetime(*args, **kw),
    )
    @patch("landscape.lib.security.subprocess.run", sample_subprocess_run_scan)
    def test_read_rkhunter_info_log_2(self, mock_datetime):
        mock_datetime.now.return_value = COMMON_DATETIME
        filename = self.makeFile(SAMPLE_RKHUNTER_LOG_2)
        rkinfo = RKHunterLogReader(filename)
        self.assertEqual(
            rkinfo.get_last_log().dict(),
            RKHunterInfo(
                version=COMMON_VERSION,
                files_checked=145,
                files_suspect=48,
                rootkit_checked=478,
                rootkit_suspect=1,
                timestamp=COMMON_DATETIME,
            ).dict(),
        )

    def test_read_rkhunter_info_log_partial_1(self):
        filename = self.makeFile(SAMPLE_RKHUNTER_LOG_PARTIAL_1)
        rkinfo = RKHunterLogReader(filename)
        self.assertEqual(rkinfo.get_last_log(), None)

    def test_read_rkhunter_info_log_partial_2(self):
        filename = self.makeFile(SAMPLE_RKHUNTER_LOG_PARTIAL_2)
        rkinfo = RKHunterLogReader(filename)
        self.assertEqual(rkinfo.get_last_log(), None)


def sample_subprocess_run_empty_scan(
    *args,
    **kwargs,
):
    if args[0][1] == "-c":
        args = ([echo_cmd, "-n", "-e", ""],)
    elif args[0][1] == "--version":
        args = ([echo_cmd, "-n", "-e", SAMPLE_RKHUNTER_VERSION],)
    return run_orig(*args, **kwargs)


class RKHunterLiveTest(BaseTestCase):
    """Test for parsing rkhunter's output."""

    def test_base_cmd_exists_and_executable(self):
        assert os.access(echo_cmd, os.X_OK)
        assert os.access(rkhunter_cmd, os.X_OK)

    @patch(
        "landscape.lib.security.subprocess.run",
        sample_subprocess_run_empty_scan,
    )
    def test_scan_failure_empty(self):
        rklive = RKHunterLiveInfo()
        self.assertEqual(rklive.execute(), None)

    @patch(
        "landscape.lib.security.datetime",
        side_effect=lambda *args, **kw: datetime(*args, **kw),
    )
    @patch("landscape.lib.security.subprocess.run", sample_subprocess_run_scan)
    def test_scan_working(self, mock_datetime):
        mock_datetime.now.return_value = COMMON_DATETIME

        rklive = RKHunterLiveInfo()
        self.assertEqual(
            rklive.execute().dict(),
            RKHunterInfo(
                version=COMMON_VERSION,
                files_checked=145,
                files_suspect=1,
                rootkit_checked=478,
                rootkit_suspect=0,
                timestamp=COMMON_DATETIME,
            ).dict(),
        )
