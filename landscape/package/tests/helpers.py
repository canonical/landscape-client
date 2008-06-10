import base64
import os

import smart


class SmartHelper(object):

    def set_up(self, test_case):
        test_case.smart_dir = test_case.make_dir()
        test_case.repository_dir = test_case.make_dir()
        create_repository(test_case.repository_dir)

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
                smart.sysconf.set("channels",
                                  {"alias": {"type": "deb-dir",
                                             "path": test_case.repository_dir}})

        test_case.Facade = Facade
        test_case.facade = Facade({"datadir": test_case.smart_dir})


PKGNAME1 = "name1_version1-release1_all.deb"
PKGNAME2 = "name2_version2-release2_all.deb"
PKGNAME3 = "name3_version3-release3_all.deb"

HASH1 = base64.decodestring("/ezv4AefpJJ8DuYFSq4RiEHJYP4=")
HASH2 = base64.decodestring("glP4DwWOfMULm0AkRXYsH/exehc=")
HASH3 = base64.decodestring("NJM05mj86veaSInYxxqL1wahods=")


def create_repository(target_dir):
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
