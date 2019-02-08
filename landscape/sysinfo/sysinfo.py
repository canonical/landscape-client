import textwrap
from logging import getLogger
import math
import os

from twisted.python.failure import Failure

from landscape.lib.log import log_failure
from landscape.lib.plugin import PluginRegistry
from landscape.lib.twisted_util import gather_results


class SysInfoPluginRegistry(PluginRegistry):
    """
    When the sysinfo plugin registry is run, it will run each of the
    registered plugins so that they get a chance to feed information
    into the registry.

    There are three kinds of details collected: headers, notes, and footnotes.

    They are presented to the user in a way similar to the following:

        Header1: Value1   Header3: Value3
        Header2: Value2   Header4: Value4

        => This is first note
        => This is the second note

        The first footnote.
        The second footnote.

    Headers are supposed to display information which is regularly
    available, such as the load and temperature of the system.  Notes
    contain eventual information, such as warnings of high temperatures,
    and low disk space.  Finally, footnotes contain pointers to further
    information such as URLs.
    """

    def __init__(self):
        super(SysInfoPluginRegistry, self).__init__()
        self._header_index = {}
        self._headers = []
        self._notes = []
        self._footnotes = []
        self._plugin_error = False

    def add_header(self, name, value):
        """Add a new information header to be displayed to the user.

        Header names can be repeated.

        Headers with value None are not returned by get_headers(), but
        they still allocate a position in the list.  This fact may be
        explored to create a deterministic ordering even when dealing
        with values obtained asynchornously.
        """
        index = self._header_index.get(name)
        if index is None:
            self._header_index[name] = len(self._headers)
            self._headers.append((name, value))
        else:
            index += 1
            self._header_index[name] = index
            self._headers.insert(index, (name, value))

    def get_headers(self):
        """Get all information headers to be displayed to the user.

        Headers which were added with value None are not included in
        the result.
        """
        return [pair for pair in self._headers if pair[1] is not None]

    def add_note(self, note):
        """Add a new eventual note to be shown up to the administrator."""
        self._notes.append(note)

    def get_notes(self):
        """Get all eventual notes to be shown up to the administrator."""
        return self._notes

    def add_footnote(self, note):
        """Add a new footnote to be shown up to the administrator."""
        self._footnotes.append(note)

    def get_footnotes(self):
        """Get all footnotes to be shown up to the administrator."""
        return self._footnotes

    def run(self):
        """Run all plugins, and return a deferred aggregating their results.

        This will call the run() method on each of the registered plugins,
        and return a deferred which aggregates each resulting deferred.
        """
        deferreds = []
        for plugin in self.get_plugins():
            try:
                result = plugin.run()
            except Exception:
                self._log_plugin_error(Failure(), plugin)
            else:
                result.addErrback(self._log_plugin_error, plugin)
                deferreds.append(result)
        return gather_results(deferreds).addCallback(self._report_error_note)

    def _log_plugin_error(self, failure, plugin):
        self._plugin_error = True
        message = "%s plugin raised an exception." % plugin.__class__.__name__
        logger = getLogger("landscape-sysinfo")
        log_failure(failure, message, logger=logger)

    def _report_error_note(self, result):
        from landscape.sysinfo.deployment import get_landscape_log_directory
        if self._plugin_error:
            path = os.path.join(get_landscape_log_directory(), "sysinfo.log")
            self.add_note(
                "There were exceptions while processing one or more plugins. "
                "See %s for more information." % path)
        return result


def format_sysinfo(headers=(), notes=(), footnotes=(), width=80, indent="",
                   column_separator="   ", note_prefix="=> "):
    """Format sysinfo headers, notes and footnotes to be displayed.

    This function will format headers notes and footnotes in a way that
    looks similar to the following:

        Header1: Value1   Header3: Value3
        Header2: Value2   Header4: Value4

        => This is first note
        => This is the second note

        The first footnote.
        The second footnote.

    Header columns will be dynamically adjusted to conform to the size
    of header labels and values.
    """

    # Indentation spacing is easier to handle if we just take it off the width.
    width -= len(indent)

    headers_len = len(headers)
    value_separator = ": "

    # Compute the number of columns in the header.  To do that, we first
    # do a rough estimative of the maximum number of columns feasible,
    # and then we go back from there until we can fit things.
    min_length = width
    for header, value in headers:
        min_length = min(min_length, len(header)+len(value)+2)  # 2 for ": "
    columns = int(math.ceil(float(width) /
                            (min_length + len(column_separator))))

    # Okay, we've got a base for the number of columns.  Now, since
    # columns may have different lengths, and the length of each column
    # will change as we compress headers in less and less columns, we
    # have to perform some backtracking to compute a good feasible number
    # of columns.
    while True:
        # Check if the current number of columns would fit in the screen.
        # Note that headers are indented like this:
        #
        #     Header:         First value
        #     Another header: Value
        #
        # So the column length is the sum of the widest header, plus the
        # widest value, plus the value separator.
        headers_per_column = int(math.ceil(headers_len / float(columns)))
        header_lengths = []
        total_length = 0
        for column in range(columns):
            # We must find the widest header and value, both to compute the
            # column length, and also to compute per-column padding when
            # outputing it.
            widest_header_len = 0
            widest_value_len = 0
            for row in range(headers_per_column):
                header_index = column * headers_per_column + row
                # There are potentially less headers in the last column,
                # so let's watch out for these here.
                if header_index < headers_len:
                    header, value = headers[header_index]
                    widest_header_len = max(widest_header_len, len(header))
                    widest_value_len = max(widest_value_len, len(value))

            if column > 0:
                # Account for the spacing between each column.
                total_length += len(column_separator)

            total_length += (widest_header_len + widest_value_len +
                             len(value_separator))

            # Keep track of these lengths for building the output later.
            header_lengths.append((widest_header_len, widest_value_len))

        if columns == 1 or total_length < width:
            # If there's just one column, or if we're within the requested
            # length, we're good to go.
            break

        # Otherwise, do the whole thing again with one less column.
        columns -= 1

    # Alright! Show time! Let's build the headers line by line.
    lines = []
    for row in range(headers_per_column):
        line = indent
        # Pick all columns for this line.  Note that this means that
        # for 4 headers with 2 columns, we pick header 0 and 2 for
        # the first line, since we show headers 0 and 1 in the first
        # column, and headers 2 and 3 in the second one.
        for column in range(columns):
            header_index = column * headers_per_column + row
            # There are potentially less headers in the last column, so
            # let's watch out for these here.
            if header_index < headers_len:
                header, value = headers[header_index]
                # Get the widest header/value on this column, for padding.
                widest_header_len, widest_value_len = header_lengths[column]
                if column > 0:
                    # Add inter-column spacing.
                    line += column_separator
                # And append the column to the current line.
                line += (header +
                         value_separator +
                         " " * (widest_header_len - len(header)) +
                         value)
                # If there are more columns in this line, pad it up so
                # that the next column's header is correctly aligned.
                if headers_len > (column+1) * headers_per_column + row:
                    line += " " * (widest_value_len - len(value))
        lines.append(line)

    if notes:
        if lines:
            # Some spacing between headers and notes.
            lines.append("")
        initial_indent = indent + note_prefix
        for note in notes:
            lines.extend(
                textwrap.wrap(note,
                              initial_indent=initial_indent,
                              subsequent_indent=" "*len(initial_indent),
                              width=width))

    if footnotes:
        if lines:
            lines.append("")
        lines.extend(indent + footnote for footnote in footnotes)

    return "\n".join(lines)
