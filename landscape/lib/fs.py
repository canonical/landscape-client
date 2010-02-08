"""File-system utils"""


def create_file(path, content):
    """Create a file with the given content.

    @param path: The path to the file.
    @param content: The content to be written in the file.
    """
    fd = open(path, "w")
    fd.write(content)
    fd.close()
