"""Warning utilities for Landscape."""

import warnings


def hide_warnings():
    """Disable printing of non-UserWarning warnings.

    This should be used for any programs that are being run by a user in a
    production environment: warnings that aren't UserWarnings are meant for
    developers.
    """
    warnings.simplefilter("ignore")
    warnings.simplefilter("default", UserWarning)
