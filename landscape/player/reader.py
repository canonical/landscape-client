import os

from landscape.lib.fs import read_file


class PayloadReader(object):
    def __init__(self, source_dir):
        self._source_dir = source_dir

    def load(self):
        result = []
        for filename in os.listdir(self._source_dir):
            full_path = os.path.join(self._source_dir, filename)
            result.append((filename, read_file(full_path)))
        return result
