import importlib
import os
from unittest import mock

import landscape.client.environment
from landscape.client.tests.helpers import LandscapeTest


class TestEnvironment(LandscapeTest):
    def reload_environment(self, env_vars):
        with mock.patch.dict(os.environ, env_vars, clear=True):
            importlib.reload(landscape.client.environment)

    def test_defaults_empty_env(self):
        self.reload_environment({})
        self.assertIsNone(landscape.client.environment.IS_SNAP)
        self.assertFalse(landscape.client.environment.IS_CORE)
        self.assertEqual(landscape.client.environment.USER, "landscape")
        self.assertEqual(landscape.client.environment.GROUP, "landscape")
        self.assertEqual(
            landscape.client.environment.DEFAULT_CONFIG, "/etc/landscape/client.conf"
        )
        self.assertEqual(
            landscape.client.environment.UA_DATA_DIR, "/var/lib/ubuntu-advantage"
        )
        self.assertEqual(landscape.client.environment.FILE_MODE, 0o640)
        self.assertEqual(landscape.client.environment.DIRECTORY_MODE, 0o750)

    def test_is_snap(self):
        self.reload_environment({"LANDSCAPE_CLIENT_SNAP": "1"})
        self.assertTrue(landscape.client.environment.IS_SNAP)
        self.assertEqual(
            "/etc/landscape-client.conf", landscape.client.environment.DEFAULT_CONFIG
        )
        self.assertEqual(
            "/var/lib/snapd/hostfs/var/lib/ubuntu-advantage",
            landscape.client.environment.UA_DATA_DIR,
        )

    def test_is_core(self):
        self.reload_environment({"SNAP_SAVE_DATA": "1"})
        self.assertTrue(landscape.client.environment.IS_CORE)

    def test_user_and_group(self):
        # LANDSCAPE_CLIENT_BUILDING unset
        self.reload_environment({"LANDSCAPE_CLIENT_USER": "not-landscape"})
        self.assertEqual("landscape", landscape.client.environment.USER)
        self.assertEqual("landscape", landscape.client.environment.GROUP)

        # LANDSCAPE_CLIENT_BUILDING unset, LANDSCAPE_CLIENT_SNAP set
        self.reload_environment(
            {"LANDSCAPE_CLIENT_USER": "not-landscape", "LANDSCAPE_CLIENT_SNAP": "1"}
        )
        self.assertEqual("root", landscape.client.environment.USER)
        self.assertEqual("root", landscape.client.environment.GROUP)

        self.reload_environment(
            {"LANDSCAPE_CLIENT_USER": "not-landscape", "LANDSCAPE_CLIENT_BUILDING": "1"}
        )
        self.assertEqual("not-landscape", landscape.client.environment.USER)
        self.assertEqual("not-landscape", landscape.client.environment.GROUP)

    def test_file_and_directory_modes_valid_octal(self):
        self.reload_environment(
            {
                "LANDSCAPE_CLIENT_FILE_MODE": "600",
                "LANDSCAPE_CLIENT_DIRECTORY_MODE": "700",
            }
        )
        self.assertEqual(landscape.client.environment.FILE_MODE, 0o600)
        self.assertEqual(landscape.client.environment.DIRECTORY_MODE, 0o700)

    def test_file_and_directory_modes_with_leading_zero(self):
        self.reload_environment(
            {
                "LANDSCAPE_CLIENT_FILE_MODE": "0644",
                "LANDSCAPE_CLIENT_DIRECTORY_MODE": "0755",
            }
        )
        self.assertEqual(landscape.client.environment.FILE_MODE, 0o644)
        self.assertEqual(landscape.client.environment.DIRECTORY_MODE, 0o755)

    def test_file_and_directory_modes_invalid_logs_warning(self):
        """Test invalid mode strings fall back to defaults and log warning."""
        with self.assertLogs() as logging_ctx:
            self.reload_environment(
                {
                    "LANDSCAPE_CLIENT_FILE_MODE": "invalid",
                    "LANDSCAPE_CLIENT_DIRECTORY_MODE": "also-invalid",
                }
            )

        self.assertEqual(landscape.client.environment.FILE_MODE, 0o640)
        self.assertEqual(landscape.client.environment.DIRECTORY_MODE, 0o750)
        self.assertIn("Found invalid FILE_MODE: invalid", logging_ctx.output[0])
        self.assertIn("Using FILE_MODE 640", logging_ctx.output[1])
        self.assertIn(
            "Found invalid DIRECTORY_MODE: also-invalid", logging_ctx.output[2]
        )
        self.assertIn("Using DIRECTORY_MODE 750", logging_ctx.output[3])
