import os
import tempfile
from unittest import TestCase, mock

from landscape.client.snap_config import (
    CONFIG_ENTRIES,
    update_ssl_cert,
    update_ssl_client_cert,
    update_ssl_client_private_key,
)


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

    def test_update_ssl_client_cert(self):
        """The client certificate contents are written to a file whose path
        is returned for ssl_client_cert."""
        result = update_ssl_client_cert("fake-client-cert")

        self.assertEqual(
            result,
            os.path.join(self.tempdir.name, "etc/ssl/certs/ssl-client-cert.crt"),
        )
        with open(result) as f:
            self.assertEqual(f.read(), "fake-client-cert")

    def test_update_ssl_client_private_key(self):
        """The client private key is written readable by its owner only, even
        when replacing a file with looser permissions."""
        key_path = os.path.join(
            self.tempdir.name,
            "etc/ssl/private/ssl-client-private-key.key",
        )
        os.makedirs(os.path.dirname(key_path))
        with open(key_path, "w") as f:
            f.write("old-key")
        os.chmod(key_path, 0o644)

        result = update_ssl_client_private_key("fake-client-key")

        self.assertEqual(result, key_path)
        with open(result) as f:
            self.assertEqual(f.read(), "fake-client-key")
        self.assertEqual(os.stat(result).st_mode & 0o777, 0o600)
