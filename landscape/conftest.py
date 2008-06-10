"""Machinery to make py.test interpret standard unittest.TestCase classes."""

from unittest import TestCase, TestResult
import doctest

import py.test


class PyTestResult(TestResult):

    def addFailure(self, test, exc_info):
        traceback = exc_info[2]
        while traceback.tb_next:
            traceback = traceback.tb_next
        locals = traceback.tb_frame.f_locals
        if "msg" in locals or "excClass" in locals:
            locals["__tracebackhide__"] = True
        msg = str(exc_info[1])
        if not msg:
            if "expr" in locals and "msg" in locals:
                msg = repr(locals["expr"])
            else:
                msg = "!?"
        raise py.test.Item.Failed, py.test.Item.Failed(msg=msg), exc_info[2]

    addError = addFailure


class PyTestCase(TestCase):

    def __init__(self, methodName="setUp"):
        super(PyTestCase, self).__init__(methodName)

    class Function(py.test.Function):
        def execute(self, target, *args):
            __tracebackhide__ = True
            self = target.im_self
            self.__init__(target.__name__)
            self.run(PyTestResult())


class PyDocTest(py.test.collect.Module):

    def __init__(self, fspath, parent=None):
        super(PyDocTest, self).__init__(fspath.basename, parent)
        self.fspath = fspath
        self._obj = None

    def run(self):
        return [self.name]

    def join(self, name):
        return self.Function(name, parent=self, obj=self.fspath)

    class Function(py.test.Function):

        def getpathlineno(self):
            code = py.code.Code(self.failed)
            return code.path, code.firstlineno

        def failed(self, msg):
            raise self.Failed(msg)

        def execute(self, fspath):
            failures, total = doctest.testfile(str(fspath),
                                               module_relative=False,
                                               optionflags=doctest.ELLIPSIS)
            if failures:
                __tracebackhide__ = True
                self.failed("%d doctest cases" % failures)


class UnitTestModule(py.test.collect.Module):

    def buildname2items(self):
        d = {}
        for name in dir(self.obj):
            testclass = None
            obj = getattr(self.obj, name)

            try:
                if (obj is not TestCase and
                    issubclass(obj, (TestCase, PyTestCase))):
                    testclass = obj
            except TypeError:
                pass

            if testclass:
                d[name] = self.Class(name, parent=self)
                if not issubclass(testclass, PyTestCase):
                    queue = [testclass]
                    while queue:
                        testclass = queue.pop(0)
                        if TestCase in testclass.__bases__:
                            bases = list(testclass.__bases__)
                            bases[bases.index(TestCase)] = PyTestCase
                            testclass.__bases__ = tuple(bases)
                            break
                        queue.extend(testclass.__bases__)
        return d


class UnitTestDirectory(py.test.collect.Directory):

    def __init__(self, *args, **kwargs):
        if getattr(self.__class__, "__first_run__", True):
            self.__class__.__first_run__ = False
        super(UnitTestDirectory, self).__init__(*args, **kwargs)

    def filefilter(self, path):
        return path.check(fnmatch="*.py") and path.basename != "conftest.py"

    def makeitem(self, basename, filefilter=None, recfilter=None):
        path = self.fspath.join(basename)
        if path.check(fnmatch="*.txt"):
            return PyDocTest(path, parent=self)
        return super(UnitTestDirectory, self).makeitem(basename,
                                                       filefilter, recfilter)


Module = UnitTestModule
Directory = UnitTestDirectory
