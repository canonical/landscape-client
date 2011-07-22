import os

from landscape.lib.fs import read_file


class PayloadReader(object):
    """A reader that reads old exchanges from the filesystem.

    @param source_dir - The directory to read old exchanges from
    """
    def __init__(self, source_dir):
        self._source_dir = source_dir

    def load(self):
        """Load old exchanges from the filesystem.

        @return: file data in the format [(filename1, file_contents1),
            (filename2, file_contents2)]
        """
        result = []
        for filename in sorted(os.listdir(self._source_dir)):
            full_path = os.path.join(self._source_dir, filename)
            result.append((filename, read_file(full_path)))
        return result
