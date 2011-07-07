import warnings

from twisted.trial.unittest import TestCase

from landscape.lib.warning import hide_warnings


class WarningTest(TestCase):
    def setUp(self):
        super(WarningTest, self).setUp()
        self.orig_filters = warnings.filters[:]

    def tearDown(self):
        super(WarningTest, self).tearDown()
        warnings.filters[:] = self.orig_filters

    def test_hide_warnings(self):
        hide_warnings()
        filters = warnings.filters[:2]

        # Warning filters are processed beginning to end, and the first filter
        # which matches a particular warning is used.

        self.assertEqual(
            filters,
            # The frontmost should "default" (i.e.  print) on UserWarnings
            [("default", None, UserWarning, None, 0),
             # The one just behind that should indicate that we should ignore
             # all other warnings.
             ("ignore", None, Warning, None, 0)])
