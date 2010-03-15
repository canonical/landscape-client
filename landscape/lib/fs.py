"""File-system utils"""


def create_file(path, content):
    """Create a file with the given content.

    @param path: The path to the file.
    @param content: The content to be written in the file.
    """
    fd = open(path, "w")
    fd.write(content)
    fd.close()


def read_file(path):
    """Return the content of the given file.

    @param path: The path to the file.
    @return content: The content of the file.
    """
    fd = open(path, "r")
    content = fd.read()
    fd.close()
    return content
