import os
import tempfile
from unittest import TestCase, mock

from landscape.client.snap_config import CONFIG_ENTRIES, update_ssl_cert


class ConfigEntriesTest(TestCase):
    def test_no_duplicate_confdb_keys(self):
        keys = [entry[0] for entry in CONFIG_ENTRIES]
        self.assertEqual(len(keys), len(set(keys)))

    def test_no_duplicate_landscape_attrs(self):
        attrs = [entry[1] for entry in CONFIG_ENTRIES]
        self.assertEqual(len(attrs), len(set(attrs)))


class UpdateSSLCertTest(TestCase):
    def setUp(self):
        super().setUp()

        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        mock.patch.dict(
            os.environ,
            {"SNAP_COMMON": self.tempdir.name},
        ).start()
        self.addCleanup(mock.patch.stopall)

    def test_update_ssl_cert_new(self):
        cert_dir = os.path.join(self.tempdir.name, "etc/ssl/certs")
        self.assertFalse(os.path.isdir(cert_dir))

        result = update_ssl_cert("fake-cert-content")

        cert_path = os.path.join(cert_dir, "ssl-public-key.crt")
        self.assertEqual(result, cert_path)
        with open(cert_path) as f:
            self.assertEqual(f.read(), "fake-cert-content")

    def test_update_ssl_cert_existing(self):
        cert_dir = os.path.join(self.tempdir.name, "etc/ssl/certs")
        os.makedirs(cert_dir)
        cert_path = os.path.join(cert_dir, "ssl-public-key.crt")
        with open(cert_path, "w") as f:
            f.write("old-cert-content")

        result = update_ssl_cert("fake-cert-content")

        self.assertEqual(result, cert_path)
        with open(cert_path) as f:
            self.assertEqual(f.read(), "fake-cert-content")
