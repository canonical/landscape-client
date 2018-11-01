#
# Copyright (c) 2006 Canonical
# Copyright (c) 2004 Conectiva, Inc.
#
# Written by Gustavo Niemeyer <gustavo@niemeyer.net>
#
# This Python module is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# This Python module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this Python module; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
import os
import sys
import copy
import re

from twisted.python.compat import StringType  # Py2: basestring, Py3: str


__all__ = ["Persist", "PickleBackend", "BPickleBackend",
           "path_string_to_tuple", "path_tuple_to_string", "RootedPersist",
           "PersistError", "PersistReadOnlyError"]


NOTHING = object()


class PersistError(Exception):
    pass


class PersistReadOnlyError(PersistError):
    pass


class Persist(object):

    """Persist a hierarchical database of key=>value pairs.

    There are three different kinds of option maps, regarding the
    persistence and priority that maps are queried.

      - hard - Options are persistent.
      - soft - Options are not persistent, and have a higher priority
           than persistent options.
      - weak - Options are not persistent, and have a lower priority
           than persistent options.

    @ivar filename: The name of the file where persist data is saved
        or None if no filename is available.

    """

    def __init__(self, backend=None, filename=None):
        """
        @param backend: The backend to use. If none is specified,
            L{BPickleBackend} will be used.
        @param filename: The default filename to save to and load from. If
            specified, and the file exists, it will be immediately
            loaded. Specifying this will also allow L{save} to be called
            without any arguments to save the persist.
        """
        if backend is None:
            backend = BPickleBackend()
        self._backend = backend
        self._hardmap = backend.new()
        self._softmap = {}
        self._weakmap = {}
        self._readonly = False
        self._modified = False
        self._config = self
        self.filename = filename
        if filename is not None and os.path.exists(filename):
            self.load(filename)

    def _get_readonly(self):
        return self._readonly

    def _set_readonly(self, flag):
        self._readonly = bool(flag)

    def _get_modified(self):
        return self._modified

    readonly = property(_get_readonly, _set_readonly)
    modified = property(_get_modified)

    def reset_modified(self):
        """Set the database status as non-modified."""
        self._modified = False

    def assert_writable(self):
        """Assert if the object is writable

        @raise: L{PersistReadOnlyError}
        """
        if self._readonly:
            raise PersistReadOnlyError("Configuration is in readonly mode.")

    def load(self, filepath):
        """Load a persisted database."""

        def load_old():
            filepathold = filepath + ".old"
            if (os.path.isfile(filepathold) and
                os.path.getsize(filepathold) > 0
                ):

                # warning("Broken configuration file at %s" % filepath)
                # warning("Trying backup at %s" % filepathold)
                try:
                    self._hardmap = self._backend.load(filepathold)
                except Exception:
                    raise PersistError("Broken configuration file at %s" %
                                       filepathold)
                return True
            return False

        filepath = os.path.expanduser(filepath)
        if not os.path.isfile(filepath):
            if load_old():
                return
            raise PersistError("File not found: %s" % filepath)
        if os.path.getsize(filepath) == 0:
            load_old()
            return
        try:
            self._hardmap = self._backend.load(filepath)
        except Exception:
            if load_old():
                return
            raise PersistError("Broken configuration file at %s" % filepath)

    def save(self, filepath=None):
        """Save the persist to the given C{filepath}.

        If None is specified, then the filename passed during construction will
        be used.

        If the destination file already exists, it will be renamed
        to C{<filepath>.old}.
        """
        if filepath is None:
            if self.filename is None:
                raise PersistError("Need a filename!")
            filepath = self.filename
        filepath = os.path.expanduser(filepath)
        if os.path.isfile(filepath):
            os.rename(filepath, filepath + ".old")
        dirname = os.path.dirname(filepath)
        if dirname and not os.path.isdir(dirname):
            os.makedirs(dirname)
        self._backend.save(filepath, self._hardmap)

    def _traverse(self, obj, path, default=NOTHING, setvalue=NOTHING):
        if setvalue is not NOTHING:
            setvalue = self._backend.copy(setvalue)
        queue = list(path)
        marker = NOTHING
        newobj = obj
        while queue:
            obj = newobj
            elem = queue.pop(0)
            newobj = self._backend.get(obj, elem)
            if newobj is NotImplemented:
                if queue:
                    path = path[:-len(queue)]
                raise PersistError("Can't traverse %r (%r): %r" %
                                   (type(obj), path_tuple_to_string(path),
                                    str(obj)))
            if newobj is marker:
                break
        if newobj is not marker:
            if setvalue is not marker:
                newobj = self._backend.set(obj, elem, setvalue)
        else:
            if setvalue is marker:
                newobj = default
            else:
                while True:
                    if len(queue) > 0:
                        if type(queue[0]) is int:
                            newvalue = []
                        else:
                            newvalue = {}
                    else:
                        newvalue = setvalue
                    newobj = self._backend.set(obj, elem, newvalue)
                    if newobj is NotImplemented:
                        raise PersistError("Can't traverse %r with %r" %
                                           (type(obj), type(elem)))
                    if not queue:
                        break
                    obj = newobj
                    elem = queue.pop(0)
        return newobj

    def _getvalue(self, path, soft=False, hard=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        marker = NOTHING
        if soft:
            value = self._traverse(self._softmap, path, marker)
        elif hard:
            value = self._traverse(self._hardmap, path, marker)
        elif weak:
            value = self._traverse(self._weakmap, path, marker)
        else:
            value = self._traverse(self._softmap, path, marker)
            if value is marker:
                value = self._traverse(self._hardmap, path, marker)
                if value is marker:
                    value = self._traverse(self._weakmap, path, marker)
        return value

    def has(self, path, value=NOTHING, soft=False, hard=False, weak=False):
        obj = self._getvalue(path, soft, hard, weak)
        marker = NOTHING
        if obj is marker:
            return False
        elif value is marker:
            return True
        result = self._backend.has(obj, value)
        if result is NotImplemented:
            raise PersistError("Can't check %r for containment" % type(obj))
        return result

    def keys(self, path, soft=False, hard=False, weak=False):
        obj = self._getvalue(path, soft, hard, weak)
        if obj is NOTHING:
            return []
        result = self._backend.keys(obj)
        if result is NotImplemented:
            raise PersistError("Can't return keys for %s" % type(obj))
        return result

    def get(self, path, default=None, soft=False, hard=False, weak=False):
        value = self._getvalue(path, soft, hard, weak)
        if value is NOTHING:
            return default
        return self._backend.copy(value)

    def set(self, path, value, soft=False, weak=False):
        assert path
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        if soft:
            map = self._softmap
        elif weak:
            map = self._weakmap
        else:
            self.assert_writable()
            self._modified = True
            map = self._hardmap
        self._traverse(map, path, setvalue=value)

    def add(self, path, value, unique=False, soft=False, weak=False):
        assert path
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        if soft:
            map = self._softmap
        elif weak:
            map = self._weakmap
        else:
            self.assert_writable()
            self._modified = True
            map = self._hardmap
        if unique:
            current = self._traverse(map, path)
            if type(current) is list and value in current:
                return
        path = path + (sys.maxsize,)
        self._traverse(map, path, setvalue=value)

    def remove(self, path, value=NOTHING, soft=False, weak=False):
        assert path
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        if soft:
            map = self._softmap
        elif weak:
            map = self._weakmap
        else:
            self.assert_writable()
            self._modified = True
            map = self._hardmap
        marker = NOTHING
        while path:
            if value is marker:
                obj = self._traverse(map, path[:-1])
                elem = path[-1]
                isvalue = False
            else:
                obj = self._traverse(map, path)
                elem = value
                isvalue = True
            result = False
            if obj is not marker:
                result = self._backend.remove(obj, elem, isvalue)
                if result is NotImplemented:
                    raise PersistError("Can't remove %r from %r" %
                                       (elem, type(obj)))
            if self._backend.empty(obj):
                if value is not marker:
                    value = marker
                else:
                    path = path[:-1]
            else:
                break
        return result

    def move(self, oldpath, newpath, soft=False, weak=False):
        if not (soft or weak):
            self.assert_writable()
        if isinstance(oldpath, StringType):
            oldpath = path_string_to_tuple(oldpath)
        if isinstance(newpath, StringType):
            newpath = path_string_to_tuple(newpath)
        result = False
        marker = NOTHING
        value = self._getvalue(oldpath, soft, not (soft or weak), weak)
        if value is not marker:
            self.remove(oldpath, soft=soft, weak=weak)
            self.set(newpath, value, weak, soft)
            result = True
        return result

    def root_at(self, path):
        """
        Rebase the database hierarchy.

        @return: A L{RootedPersist} using this L{Persist} as parent.
        """
        return RootedPersist(self, path)


class RootedPersist(object):
    """Root a L{Persist}'s tree at a particular branch.

    This class shares the same interface of L{Persist} and provides a shortcut
    to access the nodes of a particular branch in a L{Persist}'s tree.

    The chosen branch will be viewed as the root of the tree of the
    L{RootedPersist} and all operations will be forwarded to the parent
    L{Persist} as appropriate.
    """

    def __init__(self, parent, root):
        """
        @param parent: the parent L{Persist}.
        @param root: a branch of the parent L{Persist}'s tree, that
            will be used as root of this L{RootedPersist}.
        """
        self.parent = parent
        if isinstance(root, StringType):
            self.root = path_string_to_tuple(root)
        else:
            self.root = root

    readonly = property(lambda self: self.parent.readonly)
    modified = property(lambda self: self.parent.modified)

    def assert_writable(self):
        self.parent.assert_writable()

    def has(self, path, value=NOTHING, soft=False, hard=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.has(self.root + path, value, soft, hard, weak)

    def keys(self, path, soft=False, hard=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.keys(self.root + path, soft, hard, weak)

    def get(self, path, default=None, soft=False, hard=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.get(self.root + path, default, soft, hard, weak)

    def set(self, path, value, soft=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.set(self.root + path, value, soft, weak)

    def add(self, path, value, unique=False, soft=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.add(self.root + path, value, unique, soft, weak)

    def remove(self, path, value=NOTHING, soft=False, weak=False):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.remove(self.root + path, value, soft, weak)

    def move(self, oldpath, newpath, soft=False, weak=False):
        if isinstance(oldpath, StringType):
            oldpath = path_string_to_tuple(oldpath)
        if isinstance(newpath, StringType):
            newpath = path_string_to_tuple(newpath)
        return self.parent.move(self.root + oldpath, self.root + newpath,
                                soft, weak)

    def root_at(self, path):
        if isinstance(path, StringType):
            path = path_string_to_tuple(path)
        return self.parent.root_at(self.root + path)


_splitpath = re.compile(r"(\[-?\d+\])|(?<!\\)\.").split


def path_string_to_tuple(path):
    """Convert a L{Persist} path string to a path tuple.

    Examples:

        >>> path_string_to_tuple("ab")
        ("ab",)
        >>> path_string_to_tuple("ab.cd")
        ("ab", "cd"))
        >>> path_string_to_tuple("ab[0][1]")
        ("ab", 0, 1)
        >>> path_string_to_tuple("ab[0].cd[1]")
        ("ab", 0, "cd", 1)

    Raises L{PersistError} if the given path string is invalid.
    """
    if "." not in path and "[" not in path:
        return (path,)
    result = []
    tokens = _splitpath(path)
    for token in tokens:
        if token:
            if token[0] == "[" and token[-1] == "]":
                try:
                    result.append(int(token[1:-1]))
                except ValueError:
                    raise PersistError("Invalid path index: %r" % token)
            else:
                result.append(token.replace(r"\.", "."))
    return tuple(result)


def path_tuple_to_string(path):
    result = []
    for elem in path:
        if type(elem) is int:
            result[-1] += "[%d]" % elem
        else:
            result.append(str(elem).replace(".", r"\."))
    return ".".join(result)


class Backend(object):
    """
    Base class for L{Persist} backends implementing hierarchical storage
    functionality.

    Each node of the hierarchy is an object of type C{dict}, C{list}
    or C{tuple}. A node can have zero or more children, each child can be
    another node or a leaf value compatible with the backend's serialization
    mechanism.

    Each child element is associated with a unique key, that can be used to
    get, set or remove the child itself from its containing node. If the node
    object is of type C{dict}, then the child keys will be the keys of the
    dictionary, otherwise if the node object is of type C{list} or C{tuple}
    the child element keys are the indexes of the available items, or the value
    of items theselves.

    The root node object is always a C{dict}.

    For example:

        >>> backend = Backend()
        >>> root = backend.new()
        >>> backend.set(root, "foo", "bar")
        'bar'
        >>> egg = backend.set(root, "egg", [1, 2, 3])
        >>> backend.set(egg, 0, 10)
        10
        >>> root
        {'foo': 'bar', 'egg': [10, 2, 3]}
    """

    def new(self):
        raise NotImplementedError

    def load(self, filepath):
        raise NotImplementedError

    def save(self, filepath, map):
        raise NotImplementedError

    def get(self, obj, elem, _marker=NOTHING):
        """Lookup a child in the given node object."""
        if type(obj) is dict:
            newobj = obj.get(elem, _marker)
        elif type(obj) in (tuple, list):
            if type(elem) is int:
                try:
                    newobj = obj[elem]
                except IndexError:
                    newobj = _marker
            elif elem in obj:
                newobj = elem
            else:
                newobj = _marker
        else:
            newobj = NotImplemented
        return newobj

    def set(self, obj, elem, value):
        """Set the value of the given child in the given node object."""
        if type(obj) is dict:
            newobj = obj[elem] = value
        elif type(obj) is list and type(elem) is int:
            lenobj = len(obj)
            if lenobj <= elem:
                obj.append(None)
                elem = lenobj
            elif elem < 0 and abs(elem) > lenobj:
                obj.insert(0, None)
                elem = 0
            newobj = obj[elem] = value
        else:
            newobj = NotImplemented
        return newobj

    def remove(self, obj, elem, isvalue):
        """Remove a the given child in the given node object.

        @param isvalue: In case the node object is a C{list}, a boolean
            indicating if C{elem} is the index of the child or the value
            of the child itself.
        """
        result = False
        if type(obj) is dict:
            if elem in obj:
                del obj[elem]
                result = True
        elif type(obj) is list:
            if not isvalue and type(elem) is int:
                try:
                    del obj[elem]
                    result = True
                except IndexError:
                    pass
            elif elem in obj:
                obj[:] = [x for x in obj if x != elem]
                result = True
        else:
            result = NotImplemented
        return result

    def copy(self, value):
        """Copy a node or a value."""
        if type(value) in (dict, list):
            return copy.deepcopy(value)
        return value

    def empty(self, obj):
        """Whether the given node object has no children."""
        return (not obj)

    def has(self, obj, elem):
        """Whether the given node object contains the given child element."""
        contains = getattr(obj, "__contains__", None)
        if contains:
            return contains(elem)
        return NotImplemented

    def keys(self, obj):
        """Return the keys of the child elements of the given node object."""
        keys = getattr(obj, "keys", None)
        if keys:
            return keys()
        elif type(obj) is list:
            return range(len(obj))
        return NotImplemented


class PickleBackend(Backend):

    def __init__(self):
        from landscape.lib.compat import cPickle
        self._pickle = cPickle

    def new(self):
        return {}

    def load(self, filepath):
        with open(filepath, 'rb') as fd:
            return self._pickle.load(fd)

    def save(self, filepath, map):
        with open(filepath, "wb") as fd:
            self._pickle.dump(map, fd, 2)


class BPickleBackend(Backend):

    def __init__(self):
        from landscape.lib import bpickle
        self._bpickle = bpickle

    def new(self):
        return {}

    def load(self, filepath):
        with open(filepath, "rb") as fd:
            return self._bpickle.loads(fd.read())

    def save(self, filepath, map):
        with open(filepath, "wb") as fd:
            fd.write(self._bpickle.dumps(map))

# vim:ts=4:sw=4:et
