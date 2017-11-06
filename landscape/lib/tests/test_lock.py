import time
import os
import unittest

from landscape.lib import testing
from landscape.lib.lock import lock_path, LockError


class LockTest(testing.FSTestCase, unittest.TestCase):

    def setUp(self):
        super(LockTest, self).setUp()
        self.filename = self.makeFile()

    def test_lock_creates_path(self):
        self.assertFalse(os.path.isfile(self.filename))
        lock_path(self.filename)
        self.assertTrue(os.path.isfile(self.filename))

    def test_lock_with_already_locked(self):
        unlock_path = lock_path(self.filename)
        self.assertRaises(LockError, lock_path, self.filename)
        unlock_path()
        lock_path(self.filename)

    def test_lock_with_timeout(self):
        lock_path(self.filename)
        started = time.time()
        self.assertRaises(LockError, lock_path, self.filename, timeout=0.5)
        self.assertTrue(started < time.time() - 0.5)
