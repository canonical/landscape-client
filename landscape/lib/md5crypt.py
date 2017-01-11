#########################################################
# md5crypt.py
#
# 0423.2000 by michal wallace http://www.sabren.com/
# based on perl's Crypt::PasswdMD5 by Luis Munoz (lem@cantv.net)
# based on /usr/src/libcrypt/crypt.c from FreeBSD 2.2.5-RELEASE
#
# MANY THANKS TO
#
#  Carey Evans - http://home.clear.net.nz/pages/c.evans/
#  Dennis Marti - http://users.starpower.net/marti1/
#
#  For the patches that got this thing working!
#
#########################################################
"""md5crypt.py - Provides interoperable MD5-based crypt() function

SYNOPSIS

	import md5crypt.py

	cryptedpassword = md5crypt.md5crypt(password, salt);

DESCRIPTION

Compatibility wrapper for passlib.hash.md5_crypt.
"""
from landscape.lib.hashlib import md5
from passlib.hash import md5_crypt
from twisted.python.compat import _PY3


def apache_md5_crypt (pw, salt):
    # change the Magic string to match the one used by Apache
    return unix_md5_crypt(pw, salt, '$apr1$')


def unix_md5_crypt(pw, salt, magic=None):
    if _PY3 and isinstance(salt, bytes):
        salt = salt.decode('utf8') 
    return md5_crypt.encrypt(pw, salt=salt)


## assign a wrapper function:
md5crypt = unix_md5_crypt

if __name__ == "__main__":
    print(unix_md5_crypt("cat", "hat"))
