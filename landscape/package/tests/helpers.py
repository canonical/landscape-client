import base64
import os

import smart


class SmartHelper(object):

    def set_up(self, test_case):
        test_case.smart_dir = test_case.makeDir()
        test_case.repository_dir = test_case.makeDir()
        create_simple_repository(test_case.repository_dir)

    def tear_down(self, test_case):
        if smart.iface.object:
            smart.deinit()


class SmartFacadeHelper(SmartHelper):

    def set_up(self, test_case):
        super(SmartFacadeHelper, self).set_up(test_case)

        from landscape.package.facade import SmartFacade

        class Facade(SmartFacade):
            repository_dir = test_case.repository_dir

            def smart_initialized(self):
                self.reset_channels()
                self.add_channel_deb_dir(test_case.repository_dir)

        test_case.Facade = Facade
        test_case.facade = Facade({"datadir": test_case.smart_dir})


PKGNAME1 = "name1_version1-release1_all.deb"
PKGNAME2 = "name2_version2-release2_all.deb"
PKGNAME3 = "name3_version3-release3_all.deb"

HASH1 = base64.decodestring("/ezv4AefpJJ8DuYFSq4RiEHJYP4=")
HASH2 = base64.decodestring("glP4DwWOfMULm0AkRXYsH/exehc=")
HASH3 = base64.decodestring("NJM05mj86veaSInYxxqL1wahods=")
HASH4 = 'c\xc1\xe6\xe1U\xde\xb6:\x03\xcb\xb9\xdc\xee\x91\xb7"\xc9\xb1\xe4\x8f'
HASH5 = '|\x93K\xe0gx\xba\xe4\x85\x84\xd9\xf4%\x8bB\xbdR\x97\xdb\xfc'
HASH6 = '\xedt!=,\\\rk\xa7\xe3$\xfb\x06\x9c\x88\x92)\xc2\xfb\xd6'
HASH7 = 'D\xb1\xb6\xf5\xaa\xa8i\x84\x07#x\x97\x01\xf7`.\x9b\xde\xfb '

RELEASES = {"hardy": """Origin: Ubuntu
Label: Ubuntu
Codename: hardy
Version: 8.04
Date: Tue, 31 Mar 2009 13:30:02 +0000
Architectures: amd64 i386
Components: main restricted
MD5Sum:
 356312bc1c0ab2b8dbe5c67f09879497 827 main/binary-i386/Packages
 ad2d9b94381264ce25cda7cfa1b2da03 555 main/binary-i386/Packages.gz
 2f6ee66ed2d2b4115fabc8eed428e42e 78 main/binary-i386/Release
 f0fd5c1bb18584cf07f9bf4a9f2e6d92 605 main/binary-amd64/Packages
 98860034ca03a73a9face10af8238a81 407 main/binary-amd64/Packages.gz
 7e40db962fe49b6db232bf559cf6f79d 79 main/binary-amd64/Release
 99e2e7213a7fdd8dd6860623bbf700e6 538 restricted/binary-i386/Packages
 7771307958f2800bafb5cd96292308bd 384 restricted/binary-i386/Packages.gz
 8686ad9c5d83484dc66a1eca2bd8030f 84 restricted/binary-i386/Release
 99e2e7213a7fdd8dd6860623bbf700e6 538 restricted/binary-amd64/Packages
 7771307958f2800bafb5cd96292308bd 384 restricted/binary-amd64/Packages.gz
 6e24798a6089cd3a21226182784995e9 85 restricted/binary-amd64/Release
SHA1:
 1f39494284f8da4a1cdd788a3d91a048c5edf7f5 827 main/binary-i386/Packages
 e79a66d7543f24f77a9ffe1409431ae717781375 555 main/binary-i386/Packages.gz
 5fe86036c60d6210b662df3acc238e2936f03581 78 main/binary-i386/Release
 37ba69be70f4a79506038c0124293187bc879014 605 main/binary-amd64/Packages
 65dca66c72b18d59cdcf671775104e86cbe2123a 407 main/binary-amd64/Packages.gz
 c9810732c61aa7de2887b5194c6a09d0b6118664 79 main/binary-amd64/Release
 4cdb64c700f798f719f5c81ae42e44582be094c5 538 restricted/binary-i386/Packages
 190f980fd80d58284129ee050f9eb70b9590fedb 384 restricted/binary-i386/Packages.gz
 b1d1a4d57f5c8d70184c9661a087b8a92406c76d 84 restricted/binary-i386/Release
 4cdb64c700f798f719f5c81ae42e44582be094c5 538 restricted/binary-amd64/Packages
 190f980fd80d58284129ee050f9eb70b9590fedb 384 restricted/binary-amd64/Packages.gz
 4bd64fb2ef44037254729ab514d3403a65db7123 85 restricted/binary-amd64/Release
""",
            "hardy-updates": """Origin: Ubuntu
Label: Ubuntu
Codename: hardy-updates
Version: 8.04
Date: Tue, 31 Mar 2009 13:32:17 +0000
Architectures: i386 amd64
Components: main restricted
MD5Sum:
 a23ba734dc4fe7c1ec8dc960cc670b8e 1227 main/binary-i386/Packages
 2d6d271964be8000808abfa2b0e999b7 713 main/binary-i386/Packages.gz
 2f6ee66ed2d2b4115fabc8eed428e42e 78 main/binary-i386/Release
 a23ba734dc4fe7c1ec8dc960cc670b8e 1227 main/binary-amd64/Packages
 2d6d271964be8000808abfa2b0e999b7 713 main/binary-amd64/Packages.gz
 7e40db962fe49b6db232bf559cf6f79d 79 main/binary-amd64/Release
 d41d8cd98f00b204e9800998ecf8427e 0 restricted/binary-i386/Packages
 7029066c27ac6f5ef18d660d5741979a 20 restricted/binary-i386/Packages.gz
 8686ad9c5d83484dc66a1eca2bd8030f 84 restricted/binary-i386/Release
 d41d8cd98f00b204e9800998ecf8427e 0 restricted/binary-amd64/Packages
 7029066c27ac6f5ef18d660d5741979a 20 restricted/binary-amd64/Packages.gz
 6e24798a6089cd3a21226182784995e9 85 restricted/binary-amd64/Release
SHA1:
 9867c9f7ebbb5741fc589d0d4395ea8f74f3b5e4 1227 main/binary-i386/Packages
 2a7061fa162a607a63453c0360678052a38f0259 713 main/binary-i386/Packages.gz
 5fe86036c60d6210b662df3acc238e2936f03581 78 main/binary-i386/Release
 9867c9f7ebbb5741fc589d0d4395ea8f74f3b5e4 1227 main/binary-amd64/Packages
 2a7061fa162a607a63453c0360678052a38f0259 713 main/binary-amd64/Packages.gz
 c9810732c61aa7de2887b5194c6a09d0b6118664 79 main/binary-amd64/Release
 da39a3ee5e6b4b0d3255bfef95601890afd80709 0 restricted/binary-i386/Packages
 46c6643f07aa7f6bfe7118de926b86defc5087c4 20 restricted/binary-i386/Packages.gz
 b1d1a4d57f5c8d70184c9661a087b8a92406c76d 84 restricted/binary-i386/Release
 da39a3ee5e6b4b0d3255bfef95601890afd80709 0 restricted/binary-amd64/Packages
 46c6643f07aa7f6bfe7118de926b86defc5087c4 20 restricted/binary-amd64/Packages.gz
 4bd64fb2ef44037254729ab514d3403a65db7123 85 restricted/binary-amd64/Release
"""}

PACKAGES = {"hardy":
            {"restricted":
             {"amd64": """Package: kairos
Version: 0.0.8
Architecture: all
Maintainer: Free Ekanayaka <freee@debian.org>
Installed-Size: 192
Pre-Depends: libaugeas0, python-augeas, augeas-tools, jackd, rotter, monit, darkice, soma, python-remix, nfs-kernel-server, icecast2
Priority: extra
Section: admin
Filename: pool/restricted/k/kairos/kairos_0.0.8_all.deb
Size: 60768
SHA1: 1e5cc71cbd33d2b26a8feb19a48e815f271cd335
MD5sum: 5fd717ed3d15db25ffaa9d05fec62e42
Description: kairos customisation package
 This package configures and customises an kairos
 machine.

""",
              "i386": """Package: kairos
Version: 0.0.8
Architecture: all
Maintainer: Free Ekanayaka <freee@debian.org>
Installed-Size: 192
Pre-Depends: libaugeas0, python-augeas, augeas-tools, jackd, rotter, monit, darkice, soma, python-remix, nfs-kernel-server, icecast2
Priority: extra
Section: admin
Filename: pool/restricted/k/kairos/kairos_0.0.8_all.deb
Size: 60768
SHA1: 1e5cc71cbd33d2b26a8feb19a48e815f271cd335
MD5sum: 5fd717ed3d15db25ffaa9d05fec62e42
Description: kairos customisation package
 This package configures and customises an kairos
 machine.

"""},
             "main":
             {"amd64": """Package: libclthreads2
Source: clthreads
Version: 2.4.0-1
Architecture: amd64
Maintainer: Debian Multimedia Maintainers <pkg-multimedia-maintainers@lists.alioth.debian.org>
Installed-Size: 80
Depends: libc6 (>= 2.3.2), libgcc1 (>= 1:4.1.1), libstdc++6 (>= 4.1.1)
Priority: extra
Section: libs
Filename: pool/main/c/clthreads/libclthreads2_2.4.0-1_amd64.deb
Size: 12938
SHA1: dc6cb78896642dd436851888b8bd4454ab8f421b
MD5sum: 19960adb88e178fb7eb4997b47eee05b
Description: POSIX threads C++ access library
 C++ wrapper library around the POSIX threads API. This package includes
 the shared library object.

""",
              "i386": """Package: syslinux
Version: 2:3.73+dfsg-2
Architecture: i386
Maintainer: Daniel Baumann <daniel@debian.org>
Installed-Size: 140
Depends: libc6 (>= 2.7-1), syslinux-common (= 2:3.73+dfsg-2), dosfstools, mtools
Homepage: http://syslinux.zytor.com/
Priority: optional
Section: utils
Filename: pool/main/s/syslinux/syslinux_3.73+dfsg-2_i386.deb
Size: 70384
SHA1: 6edf6a7e81a5e9759270872e45c782394dfa85e5
MD5sum: ae8baa9f6c6a172a3b127af1e6675046
Description: utilities for the syslinux bootloaders
 SYSLINUX is a suite of lightweight bootloaders, currently supporting DOS FAT
 filesystems (SYSLINUX), Linux ext2/ext3 filesystems (EXTLINUX), PXE network
 booting (PXELINUX), or bootable "El Torito" ISO 9660 CD-ROMs (ISOLINUX). It
 also includes a tool, MEMDISK, which loads legacy operating systems (such as
 DOS) from these media.

"""}},
            "hardy-updates":
            {"restricted":
             {"amd64": """""",
              "i386": """"""},
             "main":
             {"amd64": """Package: rebuildd
Version: 0.3.5
Architecture: all
Maintainer: Julien Danjou <acid@debian.org>
Installed-Size: 312
Depends: python (>= 2.5), python-support (>= 0.7.1), lsb-base, python-sqlobject, python-apt
Recommends: pbuilder, python-gdchart2, python-webpy
Suggests: cowdancer
Priority: extra
Section: devel
Filename: pool/main/r/rebuildd/rebuildd_0.3.5_all.deb
Size: 24652
SHA1: 5446cd5c8a29212b403214884cae96f14824a573
MD5sum: 92e81240c2caf286ad103e44dcdc44e1
Description: build daemon aiming at rebuilding Debian packages
 This software allows you to manage a set of jobs. Each job is a package
 rebuilding task. Rebuilding is done by pbuilder (or cowbuilder if you want),
 or anything else, since everything is customizable via configuration file.
 It can also send build logs by email, event each log can be sent to a different
 email address.
 .
 rebuildd is multi-threaded, so you can run multiple build jobs in parallel.
 It is also administrable via a telnet interface. A Web interface is also
 embedded so you can see your jobs queue and watch log file in real-time in your
 browser.
 .
 rebuildd is designed to be run on multiple hosts even with different
 architecture set, and to parallelize the rebuild tasks.

""",
              "i386": """Package: rebuildd
Version: 0.3.5
Architecture: all
Maintainer: Julien Danjou <acid@debian.org>
Installed-Size: 312
Depends: python (>= 2.5), python-support (>= 0.7.1), lsb-base, python-sqlobject, python-apt
Recommends: pbuilder, python-gdchart2, python-webpy
Suggests: cowdancer
Priority: extra
Section: devel
Filename: pool/main/r/rebuildd/rebuildd_0.3.5_all.deb
Size: 24652
SHA1: 5446cd5c8a29212b403214884cae96f14824a573
MD5sum: 92e81240c2caf286ad103e44dcdc44e1
Description: build daemon aiming at rebuilding Debian packages
 This software allows you to manage a set of jobs. Each job is a package
 rebuilding task. Rebuilding is done by pbuilder (or cowbuilder if you want),
 or anything else, since everything is customizable via configuration file.
 It can also send build logs by email, event each log can be sent to a different
 email address.
 .
 rebuildd is multi-threaded, so you can run multiple build jobs in parallel.
 It is also administrable via a telnet interface. A Web interface is also
 embedded so you can see your jobs queue and watch log file in real-time in your
 browser.
 .
 rebuildd is designed to be run on multiple hosts even with different
 architecture set, and to parallelize the rebuild tasks.

"""}}}


def create_simple_repository(target_dir):
    """
    Create a simple APT repository with a single Packages.gz in C{target_dir}.
    """
    filename = os.path.join(target_dir, "Packages.gz")
    file = open(filename, "w")
    file.write(base64.decodestring("""
H4sICOl+gUUAA1BhY2thZ2VzAL2TTY/TMBCG7/4VOcJhF3vsOHYEiBUrPg6gaitxrfwxKRFNUpyk
Uvn1zLZNW2h3uREp0vjNOx8aP5m58MMtscxa16Bgs1R3qR62Zdath7pr3YrNMTxGZfYxdeNasM9t
P7jVCuPNvP5FiWDYF1e3A72YyDXS502Xfa2xwS2m7PVyr7xrD8pti8NbdpfC93qg2mOiIlSQfcPU
7xpt9oG4SbhC1+/G6jZ1xL7M1odoP+49rrGNJCf8OdYJd2r24s10niq9pAp4c3SvE/6dcJJOOQ8Y
uqaZGkzxWY9JOqXMx+US+4ES+kN0tE/Cyfy+a6tVHR7dYQqP9qNy8n+oV7uBy+z21c63uNjUghZ5
G9Gz/d0ILul27vN+bMoMKzQSPXhjBVfaSy6dqywYEYRCjWz+6U6UmVfoQwTPlZWcG5ODUzZXGIPk
DqSOudBBU12yQ67LrDLWBu8AfGELw6NH6+kxHKrKcuELVBIU5AG0iqEA1N4DD5xrgaoCTbfYh1Sv
95TNx6ZxaStYdiYLxmbnoMK/QYX/BypM64cnQIWroMIlqPAsqHAVVHgOVLgKKjwFKlwBFZ4GFa6B
CpegwuJiU8+BWhVKEScqWB1UIMZQF1xzwSNhZ/JwALUqrNJGgBSYW3Aiz00RPbHqfCy0k0VEpEx3
BJUYrYSyVusAlUY60b8QKgLUOeEj5toYTnQKGSXYPFghLddFkEJHg6iuggp/gAqM/QayJ50UUgUA
AA==
    """))
    file.close()

    filename = os.path.join(target_dir, PKGNAME1)
    file = open(filename, "w")
    file.write(base64.decodestring("""
ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMTAwNjQ0ICA0
ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ0OTMgIDAgICAgIDAgICAgIDEw
MDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UQW+bMBQHcM58Ch+7QwCbEJpomzat0rTDpmiR
enfNC7EGNnuGSOmnnwMlyVK1O6VT1feTkJ+e/wRh40RxcHGJl2dZP3rnY1/zJJsmIs9Fvs/5UQQs
C15A51qJjAVobftc7l/zr1QU10XmutpdeP9n0+mT+8+5+Hv/fSOdBiyh/b84MYM1n2fz7G4t0+u5
SvMkhbTgs3wu+CwBxjqHsdtIhLiwKjayBh6rjTQlVLaMbuBOSxOV92FAXuX5V9a0aKv/eP5zkZyf
/1TQ+X8RS6l+yRIWrD/Y4S2g09Ys2HYo+AShAun81ApU2099Rds1PFyitqjb3YLZZj8hq/Azqo1u
fa5D/4uyqnwIJjfQgCncgjUICL87jdA/jF19OGmND3wXHvLn4UfJn6BsXY/hsT7Jj63jLauuLMG1
/gb3UB3iY+MY/mLNutJqn1ZjeYgfOsf8Eu1WF9C/6lANq/rN+I+sqqCYrPS9XxlxHX6X2rT+AvQL
uv8Gt5b90FDDDpC9L4fOJ/PQiQy0H/3COIW6GXZh1dW1xB0P2Umb078wIYQQQgghhBBCCCGEEEII
IYS8UX8AYydx2gAoAABkYXRhLnRhci5neiAgICAgMTE2NjExNDQ5MyAgMCAgICAgMCAgICAgMTAw
NjQ0ICAzOTQgICAgICAgYAofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5kDlIH
pI0YFEwZ6ABKi0sSixQUGIry80vwqSMkP0SBnn5pcZH+YIp/EwYDIMd4NP7pGP/FGYlFqfqDJ/4N
zYxNRuOf3vGfkp+sPzji38jEwHA0/gci/vMSc1MN9Qc6/o2B7NH4H7j4T85IzEtPzclP13NJTcpM
zNNLr6Iw/s1MTHDGv5GxOSz+zUxNjYDxbw7kMSgYjMY/zYF8NwdHVm2jKxMzepwz6J7y5jpkIOH6
sDKssF1rmUqYzBX2piZj9zyFad5RHv8dLoXsqua2spF3v+PQffXIlN8aYepsu3x2u0202VX+QFC1
0st6vvMfDdacgtdzKtpe5G5tuFYx5elcpXm27Od8LH7Oj3mqP7VgD8P6dTmJ33dsPnpuBnPO3SvL
DNlu6ay9It6yZon0BIZRMApGwSgYBaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgFo2AUjIJRMApG
AUkAADhX8vgAKAAA
    """))
    file.close()

    filename = os.path.join(target_dir, PKGNAME2)
    file = open(filename, "w")
    file.write(base64.decodestring("""
ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMTAwNjQ0ICA0
ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjYxMTQ1MjIgIDAgICAgIDAgICAgIDEw
MDY0NCAgNDUyICAgICAgIGAKH4sIAAAAAAAAA+3UTY/TMBAG4JzzK3yEQ/Phxk1aAQKxEuIAqrYS
d+NMU4vEDuOkUvfX4yabthQBpy5aMY9UZTR+06ieuFEc3Fzi5UIMV+/6OtRpIrKE5/l8zn0/z9Ms
YCJ4Ar3rJDIWoLXdn3J/W3+morgphesbd+P5L7Lst/NPU/7z/H2DLwKW0PxvrixSlYkiAVGIxZJn
aSHFdilUDplabnnGWO8wdjuJEJdWxUY2wGO1k6aC2lbRHXzV0kTVQxiQZ3n+lTUd2vofnv+cJ9fn
f57S+X8Sa6m+yQpWbDjY4RdAp61Zsf1Y8BlCDdL5pQ2oblj6gLZvebhGbVF3hxWz7XFB1uE7VDvd
+VyP/htlXfsQzO6gBVO6FWsREL73GmF4GHvx+qI1PfBleMpfh39J3oOyTTOFp/oiP7XOt2z6qgLX
+RvcY3WKT41z+L0121qrY1pN5Sl+6pzza7R7XcLwU8dq3NWPxr9kdQ3lbKMf/M7wIvwkten8B9Bv
6PEd3Fv2WUMDB0D2qho7b81jJzLQvfEb4xTqdpzCpm8aiQcesos2p39hQgghhBBCCCGEEEIIIYQQ
Qgj5T/0AyM2cyQAoAABkYXRhLnRhci5neiAgICAgMTE2NjExNDUyMiAgMCAgICAgMCAgICAgMTAw
NjQ0ICAzOTMgICAgICAgYAofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqYmBkbm5sbAgU
Nzc3NGZQMGWgAygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDLP6BHCOT0finX/wXZyQWpeoPnvg3
NDMyG41/esd/Sn6y/uCIfyNj89Hyf0DiPy8xN9VIf6Dj39jY3HQ0/gcu/pMzEvPSU3Py0/VcUpMy
E/P00qsojH8zExOc8Q/M7Yj4Bxb8BobmBsDkomAwGv80B/LdHBzX6hpdmZjR45xB99RGrkMGEq4P
bf0L3UWDL4XIRIk6Hjx7Urzj6SSxS/YTzKbu28sqe/64oPmFJGPj3lqR1cLMdz12u04rLHp/gM2y
0mv3HOc/GqxvCl7PqWh7kbux6VrFk69zlefZsuv5WPycH/NUv7VgF8N6vfeBcgXp3NlnBFNDw5eZ
sd1as/aK+JzyvZ0TGEbBKBgFo2AUjIJRMApGwSgYBaNgFIyCUTAKRsEoGAWjYBSMglEwCkbBKBgF
JAEAu4OlKQAoAAAK
    """))
    file.close()

    filename = os.path.join(target_dir, PKGNAME3)
    file = open(filename, "w")
    file.write(base64.decodestring("""
ITxhcmNoPgpkZWJpYW4tYmluYXJ5ICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMTAwNj
Q0ICA0ICAgICAgICAgYAoyLjAKY29udHJvbC50YXIuZ3ogIDExNjkxNDgyMDMgIDAgICAg
IDAgICAgIDEwMDY0NCAgNDUxICAgICAgIGAKH4sIAAAAAAAAA+3UwY7TMBAG4JzzFD7CoU
kax7iqYAViJcQBVFGJu3GmqbWJHcZJpe7T4yabtnS1cOqiFfNJVUbjP43qiZuk0dVlgRRi
uAaX16GeZ0JwWRSF4KEvZc4jJqJn0PtOIWMROtf9Kfe39RcqSZtS+L7xV57/m6J4cv7zef
77/EODi4hlNP+r4yIrc1mUUs43C1VmhcxLEAKkFouCbzRjvcfUbxVCWjqdWtUAT/VW2Qpq
VyW38MMom1T3cURe5PnXznbo6n94/mWeXZ5/ntP5fxYrpe9UBUs2HOz4O6A3zi7Zbiz4DK
EG5cPSGnQ3LH1C17c8XqFxaLr9krn2sKDq+APqrelCrsfwjaquQwhmt9CCLf2StQgIP3uD
MDyMvXp31poe+Do+5i/Dj5LfQLummcJTfZafWqdb1n1Vge/CDf6hOsanxin80dlNbfQhra
fyGD92TvkVup0pYfipYzXu6mcbXrK6hnK2NvdhZ/JF/EUZ24UPYNjQwzu4c+yrgQb2gOxt
NXbe24dOYqG7CRvjNZp2nMK6bxqFex6zszanf2FCCCGEEEIIIYQQQgghhBBCCPlP/QK+dA
1dACgAAApkYXRhLnRhci5neiAgICAgMTE2OTE0ODIwMyAgMCAgICAgMCAgICAgMTAwNjQ0
ICAzOTkgICAgICAgYAofiwgAAAAAAAAD09NnoDkwAAJzU1MwDQToNJhtaGBqamxuYmJiag
QUNzc3MmJQMGWgAygtLkksUlBgKMrPL8GnjpD8EAV6+qXFRfqDKf4NGQyAHOPR+Kdj/Bdn
JBal6g+e+Dc0MzYZjX96x39KfrL+4Ih/IxMDw9H4H4j4z0vMTTXWH8j4B9b/hsYmBqaj8T
9w8Z+ckZiXnpqTn67nkpqUmZinl15FYfybmZjgjH8jY3NE/JuYAePfHKieQcFgNP5pDuS7
OTjUTq53ZWJGj3MG3VPeXIcMJFwfVoYVtmstW+Imc4W9qcnYPU9hmneUx3+HSyG7qrmtbO
Td7zh0Xz0y5bdGmDrbLp/dbhNtdpU/EFSt9LKe7/xHgzWn4PWcirYXuVsbrlVMeTpXaZ4t
+zkfi5/zY57qTy3Yw7B+XU7g+8L07rmG7Fe2bVxmyHZLZ+0V8Sl2Xj8mMIyCUTAKRsEoGA
WjYBSMglEwCkbBKBgFo2AUjIJRMApGwSgYBaNgFIyCUTAKSAIAY/FOKAAoAAAK
    """))
    file.close()


def create_full_repository(target_dir):
    """
    Create a full APT repository with a dists/ tree rooted at C{target_dir}.
    """

    class Repository(object):

        codename = "hardy"
        variant = "updates"
        components = "main restricted"
        archs = ["amd64", "i386"]
        hashes = [HASH4, HASH5, HASH6, HASH7]

        def __init__(self, root):
            self.root = root
            self.url = "file://%s" % self.root

    repository = Repository(target_dir)
    dists_directory = os.path.join(repository.root, "dists")
    os.mkdir(dists_directory)
    for dist in [repository.codename,
                 "%s-%s" % (repository.codename, repository.variant)]:
        dist_directory = os.path.join(dists_directory, dist)
        os.mkdir(dist_directory)
        fd = open(os.path.join(dist_directory, "Release"), "w")
        fd.write(RELEASES[dist])
        fd.close()
        for component in repository.components.split():
            component_directory = os.path.join(dist_directory, component)
            os.mkdir(component_directory)
            for arch in repository.archs:
                arch_directory = os.path.join(component_directory,
                                              "binary-%s" % arch)
                os.mkdir(arch_directory)
                fd = open(os.path.join(arch_directory, "Packages"), "w")
                fd.write(PACKAGES[dist][component][arch])
                fd.close()
                fd = open(os.path.join(arch_directory, "Release"), "w")
                fd.write("""Version: 8.04
Component: %s
Origin: Ubuntu
Label: Ubuntu
Architecture: %s
""" % (component, arch))
                fd.close()
    return repository
