from unittest import TestCase
from unittest.mock import Mock
from unittest.mock import patch

from landscape.client.snap.http import SnapdHttpException
from landscape.client.snap.http import SnapHttp


class SnapHttpTestCase(TestCase):
    def test_get_snaps(self):
        """get_snaps() returns a dict with a list of installed snaps."""
        http = SnapHttp()
        result = http.get_snaps()["result"]

        self.assertTrue(isinstance(result, list))
        self.assertGreater(len(result), 0)

        first = result[0]
        for key in ("id", "name", "publisher"):
            self.assertIn(key, first)

    def test_get_snaps_error_code(self):
        """
        get_snaps raises a SnapdHttpException if the response code from
        the snapd HTTP service is >= 400
        """
        http = SnapHttp()

        with patch("pycurl.Curl") as curl_mock:
            getinfo_mock = Mock(return_value=400)
            curl_mock.return_value = Mock(getinfo=getinfo_mock)

            self.assertRaises(SnapdHttpException, http.get_snaps)

    def test_get_snaps_couldnt_connect(self):
        """
        get_snaps raises a SnapdHttpException if we cannot reach the
        snapd HTTP service.
        """
        http = SnapHttp(snap_socket="/run/garbage.socket")

        self.assertRaises(SnapdHttpException, http.get_snaps)
