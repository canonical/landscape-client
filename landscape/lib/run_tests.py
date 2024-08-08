if __name__ == "__main__":
    # Patch Twisted Trial's `_AdaptedReporter` to add the Python 3.12-expected
    # `addDuration` method. This eliminates a large amount of emitted warnings,
    # and should no longer be necessary once
    # https://github.com/twisted/twisted/issues/12229 is fixed.
    import sys
    from twisted.trial.reporter import _AdaptedReporter
    from twisted.scripts.trial import run

    def _addDuration(self, _test, _elapsed):
        pass

    _AdaptedReporter.addDuration = _addDuration

    sys.exit(run())
