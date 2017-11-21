"""
The accumulation logic generates data points for times that are a
multiple of a step size.  In other words, if the step size is 300
seconds, any data reported by the accumulation code will always be for
a timestamp that is a multiple of 300.  The purpose of this behaviour
is to (a) limit the amount of data that is sent to the server and (b)
provide data in a predictable format to make server-side handling of
the data straight-forward.  A nice side-effect of providing data at a
known step-interval is that the server can detect blackholes in the
data simply by testing for the absence of data points at step
intervals.

Limiting the amount of data sent to the server and making the data
format predictable are both desirable attributes, but we need to
ensure the data reported is accurate.  We can't rely on plugins to
report data exactly at step boundaries and even if we could we
wouldn't necessarily end up with data points that are representative
of the resource being monitored.  We need a way to calculate a
representative data point from the set of data points that a plugin
provided during a step period.

Suppose we want to calculate data points for timestamps 300 and 600.
Assume a plugin runs at an interval less than 300 seconds to get
values to provide to the accumulator.  Each value received by the
accumulator is used to update a data point that will be sent to the
server when we cross the step boundary.  The algorithm, based on
derivatives, is:

  (current time - previous time) * value + last accumulated value

If the 'last accumulated value' isn't available, it defaults to 0.
For example, consider these timestamp/load average measurements:
300/2.0, 375/3.0, 550/3.5 and 650/0.5.  Also assume we have no data
prior to 300/2.0.  This data would be processed as follows:

  Input       Calculation                   Accumulated Value
  -----       -----------                   -----------------
  300/2.0     (300 - 300) * 2.0 + 0         0.0

  375/3.0     (375 - 300) * 3.0 + 0.0       225.0

  550/3.5     (550 - 375) * 3.5 + 225.0     837.5

  650/0.5     (600 - 550) * 0.5 + 837.5     862.5

Notice that the last value crosses a step boundary; the calculation
for this value is:

  (step boundary time - previous time) * value + last accumulated value

This yields the final accumulated value for the step period we've just
traversed.  The data point sent to the server is generated using the
following calculation:

  accumulated value / step interval size

The data point sent to the server in our example would be:

  862.5 / 300 = 2.875

This value is representative of the activity that actually occurred
and is returned to the plugin to queue for delivery to the server.
The accumulated value for the next interval is calculated using the
portion of time that crossed into the new step period:

  Input       Calculation                   Accumulated Value
  -----       -----------                   -----------------
  650/0.5     (650 - 600) * 0.5 + 0         25

And so the logic goes, continuing in a similar fashion, yielding
representative data at each step boundary.
"""


class Accumulator(object):

    def __init__(self, persist, step_size):
        self._persist = persist
        self._step_size = step_size

    def __call__(self, new_timestamp, new_free_space, key):
        previous_timestamp, accumulated_value = self._persist.get(key, (0, 0))
        accumulated_value, step_data = \
            accumulate(previous_timestamp, accumulated_value,
                       new_timestamp, new_free_space, self._step_size)
        self._persist.set(key, (new_timestamp, accumulated_value))
        return step_data


def accumulate(previous_timestamp, accumulated_value,
               new_timestamp, new_value,
               step_size):
    previous_step = previous_timestamp // step_size
    new_step = new_timestamp // step_size
    step_boundary = new_step * step_size
    step_diff = new_step - previous_step
    step_data = None

    if step_diff == 0:
        diff = new_timestamp - previous_timestamp
        accumulated_value += diff * new_value
    elif step_diff == 1:
        diff = step_boundary - previous_timestamp
        accumulated_value += diff * new_value
        step_value = float(accumulated_value) / step_size
        step_data = (step_boundary, step_value)
        diff = new_timestamp - step_boundary
        accumulated_value = diff * new_value
    else:
        diff = new_timestamp - step_boundary
        accumulated_value = diff * new_value

    return accumulated_value, step_data
