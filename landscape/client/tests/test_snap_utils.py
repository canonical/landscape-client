from unittest import mock
from unittest import TestCase

import yaml

from landscape.client.snap_http import SnapdHttpException
from landscape.client.snap_http import SnapdResponse
from landscape.client.snap_utils import get_assertions


TEST_SERIAL_ASSERTION = """type: serial
authority-id: canonical
brand-id: canonical
model: pc-amd64
serial: 03961d5d-26e5-443f-838d-6db046126bea
device-key:
    AcbBTQRWhcGAARAA0y/BXkBJjPOl24qPKOZWy7H+6+piDPtyKIGfU9TDDrFjFnv3R8EMTz1WNW8
    5nLR8gjDXNh3z7dLIbSPeC54bvQ7LlaO2VYICGdzHT5+68Rod9h5NYdTKgaWDyHdm2K1v2oOzmM
    Z+MmL15TvP9lX1U8OIVkmHhCO7FeDGsPlsTX2Wz++SrOqG4PsvpYsaYUTHE+oZ+Eo8oySW/OxTm
    rQIEUoDEWNbFR5/+33tHRDxKSjeErCVuVetZxlZW/gpCx5tmCyAcBgKoEKsPqrgzW4wUAONaSOG
    Zuo35DxwqeGHOx3C118rYrGvqA2mCn3fFz/mqnciK3JzLemLjw4HyVd1DyaKUgGjR6VYBcadL72
    YN6gPiMMmlaAPtkdFIkqIp1OpvUFEEEHwNI88klM/N8+t3JE8cFpG6n4WBdHUAwtMmmVxXm5IsM
    uNwrZdIBUu4WOAAgu2ZioeHLIQlDGw6dvVTaK+dTe0EXo5j+mH5DFnn0W1L7IAj6rX8HdiM5X5f
    4kwiezSfYXJgctdi0gizdGB7wcH0/JynaXA/tI3fEVDu45X7dA/XnCEzYkBxpidNfDkmXxSWt5N
    NMuHZqqmNHNfLeKAo1yQ/SH702nth6vJYJaIX4Pgv5cVrX5L429U5SHV+8HaE0lPCfFo/rKRJa9
    rvnJ5OGR4TeRTLsAEQEAAQ==
device-key-sha3-384: _4U3nReiiIMIaHcl6zSdRzcu75Tz37FW8b7NHhxXjNaPaZzyGooMFqur0E
timestamp: 2016-11-08T18:16:12.977431Z
sign-key-sha3-384: BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0hqUel3

AcLBUgQAAQoABgUCWCIWcgAARegQAB4/UsBpzqLOYOpmR/j9BX5XNyEWxOWgFg5QLaY+0bIz/nbU
avFH4EwV7YKQxX5nGmt7vfFoUPsRrWO4E6RtXQ1x5kYr8sSltLIYEkUjHO7sqB6gzomQYkMnS2fI
xOZwJs9ev2sCnqr9pwPC8MDS5KW5iwXYvdBP1CIwNfQO48Ys8SC9MdYH0t3DbnuG/w+EceOIyI3o
ilkB427DiueGwlBpjNRSE4B8cvglXW9rcYW72bnNs1DSnCq8tNHHybBtOYm/Y/jmk7UGXwqYUGQQ
Iwu1W+SgloJdXLLgM80bPzLy+cYiIe1W1FSMzVdOforTkG5mVFHTL/0l4eceWequfcxU3DW9ggcN
YJx8MPW9ab5gPibx8FeVb6cMWEvm8S7wXIRSff/bkHMhpjAagp+A6dyYsuUwPXFxCvHSpT0vUwFS
CCPHkPUwj54GjKAGEkKMx+s0psQ3V+fcZgW5TBxk/+J83S/+6AiQ06W8rkabWCRyl2fX81vMBynQ
nu147uRGWTXfa31Mys9lAGNHMtEcMmA106f2XfATqNK99GlIIjOxqEe5zH3j51JtY+5kyJd9cqvl
Pb0rZnPySeGxnV4Q2403As67AJrIExRrcrK2yXZjEW3G2zTsFNzBSSZr0U8id1UJ/EZLB/em2EHw
D2FXTwfDiwGroHYUFAEu1DkHx7Sy
"""

TEST_DECLARATION_ASSERTIONS = """type: snap-declaration
format: 1
authority-id: canonical
revision: 6
series: 16
snap-id: ffnH0sJpX3NFAclH777M8BdXIWpo93af
plugs:
  hardware-observe:
    allow-auto-connection: true
  mount-observe:
    allow-auto-connection: true
  network-observe:
    allow-auto-connection: true
  scsi-generic:
    allow-auto-connection: true
  shutdown:
    allow-auto-connection: true
  snapd-control:
    allow-auto-connection: true
    allow-installation: true
  system-observe:
    allow-auto-connection: true
publisher-id: 0N0rjFmfHsjIZMCjZ4IX5EtW2CsVd5Ky
snap-name: landscape-client
timestamp: 2023-11-08T07:46:21.082809Z
sign-key-sha3-384: BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0hqU

AcLBUgQAAQoABgUCZUs80QAA5QQQALZTjK8YeaJIVjcDw4w7IbLyfO28hQEy95ocZOWLtPwnSYQk
OJBtSFknwTCGKvlaOFuy9PLIABG+MoObm+MOQ8QjqqgHZ+ESqCs5sHrpYk2U9nhI6h89iDshk6Sg
T9l0tqqyV5pEen9nH/zRJy6k8xm7iMR7y1DVl4PBFJVwmugyXn1/4/kG5XKwV1p4WdvIemPzk7nm
nNvVpx+T2IAbXCcZMnvXxmCIf+KqiIub3v4Cvpy9xyxNGqLdCHiCh9bsPoTz2lwHOpgki/rlS6gd
T+GZZf+0358Xom5CeLMMVlV/1jcZs3X0BTK5m2Tx5aW4f+4pHfSi7idtaV1lzqUagM+KO/UdGi7i
dxq1/6eP0YTDb/hHhjlhDQAgwBTCvxRDor8V/NE1TkdEsbMFMgEOT/70v6mkgpXXYY9gnEg0vlSW
osDXzqN6tchJzVQfYYPRjIplX3C+fF5axCUL/ly14Up558ge53zS6frImytG/Qxeh0Ga1RyJsqMu
mbmz+uHwQA2IuXU9MbubCzO6hvVP4zU8FKbSRLrXrSLOwxuFFFRU5aor/w+kbx3l/pgfzOkpSLgD
eEQQbEjwhN14cCTq+jt78MoIAVLMHj1cre567X6ei1HufpAYRdAEL5Igi3+8ua5AyI3QTp7mQIPm
UUvllJovZRye6mF0u7VK9YRQwaoY

type: snap-declaration
authority-id: canonical
series: 16
snap-id: XaUSoE9KNKazeLO5H02NMM2cTxX8E9IH
publisher-id: f22PSauKuNkwQTM9Wz67ZCjNACuSjjhN
snap-name: pocketses
timestamp: 2024-01-03T11:01:29.918417Z
sign-key-sha3-384: BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0hqU

AcLBUgQAAQoABgUCZZU+iQAA8GsQADl85AbacovxCOrCb3zNDCCBulAakWiITOTd6lCPkibQq+2b
5Nj7PUl+DCqnVBr8tWx/o8Me/Q4yC+btcOZA/LIzCFHVXS/ExvKABSthgIjygkwM4BbXWpdm7Fua
CxY3GzsfBbOQncpOV/jN5UmoCPJ+/OBJleoxjboZGeMr7hEaKhMKed0+C1VXGVJnpL8MfdDjOgjz
WWSJX+KVfQhNIUZJVGMdJ6tl3/Dzs2wSnwfy8mftx0eXWB2Z9xnX17lWe/ewqG38DzYcoq2dbkNU
XItff1HdEJZANbmW1f2vRbeeShDUvW9mxHcYauI+VsBr5XiHDGO8h4l7kDrlh76j/th5y/WSOGyN
DEV/E5Q+JDUFy0k9NSgw6pCHY7EwOwyiM0zKe4wEUhuLUvIuO9n4lAUApIgxNvDgxx7ZymHggzHy
HQZEt8GwUBNgipqz1FI4u5eT2LhhqwVT6no2dmVwVTUxaPPRKxM3qApUzXzzzLJxNKf5XeM0/QFW
aYy6QoXO3X0Ze01DFq2aFqXsNi4flpONFDG3fsffXCoxyPRaXpB3bRXuRTN0oAun7IxF/m2KHZyn
Xl40RI/40APrJpUUgJu9QjXslspuX9X6JUNjdwUVs65qbfVvdjUMKcIkk/CX14YKquPXrIzwOaao
EJ67KJVjhdyWDv+AUE4FMC0hUGSh
"""


class AssertionTest(TestCase):
    def setUp(self):
        super().setUp()

        self.snap_http = mock.patch(
            "landscape.client.snap_utils.snap_http",
        ).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_get_assertions_one_result(self):
        self.snap_http.get_assertions.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            result=TEST_SERIAL_ASSERTION.encode(),
        )

        assertions = get_assertions("serial")
        self.assertEqual(len(assertions), 1)
        self.assertEqual(assertions[0]["type"], "serial")
        self.assertEqual(
            assertions[0]["serial"],
            "03961d5d-26e5-443f-838d-6db046126bea",
        )
        self.assertEqual(assertions[0]["model"], "pc-amd64")
        self.assertEqual(
            assertions[0]["sign-key-sha3-384"],
            "BWDEoaqyr25nF5SNCvEv2v7QnM9QsfCc0PBMYD_i2NGSQ32EF2d4D0hqUel3",
        )

    def test_get_assertions_multiple_results(self):
        self.snap_http.get_assertions.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            result=TEST_DECLARATION_ASSERTIONS.encode(),
        )

        assertions = get_assertions("snap-declaration")
        self.assertEqual(len(assertions), 2)
        self.assertEqual(assertions[0]["snap-name"], "landscape-client")
        self.assertEqual(assertions[1]["snap-name"], "pocketses")

    def test_get_assertions_no_result(self):
        self.snap_http.get_assertions.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            result=b"",
        )

        assertions = get_assertions("serial-request")
        self.assertEqual(assertions, [])

    def test_get_assertions_exception(self):
        self.snap_http.get_assertions.side_effect = SnapdHttpException()

        assertions = get_assertions("unknown")
        self.assertIsNone(assertions)

    def test_get_assertions_invalid_assertion(self):
        bad_assertion = "assertion-header: {{ bad-val }}\n\nsignature"
        self.snap_http.get_assertions.return_value = SnapdResponse(
            "sync",
            200,
            "OK",
            result=bad_assertion.encode(),
        )

        with self.assertRaises(yaml.constructor.ConstructorError):
            get_assertions("serial")
