import os
import time
import logging

from twisted.internet.defer import fail, DeferredList, succeed
from twisted.python.compat import iteritems

from landscape.lib.scriptcontent import generate_script_hash
from landscape.lib.user import get_user_info, UnknownUserError
from landscape.client.accumulate import Accumulator
from landscape.client.manager.plugin import ManagerPlugin
from landscape.client.manager.scriptexecution import (
    ProcessFailedError, ScriptRunnerMixin, ProcessTimeLimitReachedError)


class StoreProxy(object):
    """
    Persist-like interface to store graph-points into SQLite store.
    """

    def __init__(self, store):
        self.store = store

    def get(self, key, default):
        graph_accumulate = self.store.get_graph_accumulate(key)
        if graph_accumulate:
            return graph_accumulate[1:]
        else:
            return default

    def set(self, key, value):
        self.store.set_graph_accumulate(key, value[0], value[1])


class InvalidFormatError(Exception):

    def __init__(self, value):
        self.value = value
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return u"Failed to convert to number: '%s'" % self.value


class NoOutputError(Exception):

    def __init__(self):
        Exception.__init__(self, u"Script did not output any value")


class ProhibitedUserError(Exception):
    """
    Raised when an attempt to run a script as a user that is not allowed.

    @ivar username: The username that was used
    """

    def __init__(self, username):
        self.username = username
        Exception.__init__(self, self._get_message())

    def _get_message(self):
        return (u"Custom graph cannot be run as user %s" % self.username)


class CustomGraphPlugin(ManagerPlugin, ScriptRunnerMixin):
    """
    Manage adding and deleting custom graph scripts, and then run the scripts
    in a loop.

    @param process_factory: The L{IReactorProcess} provider to run the
        process with.
    """
    run_interval = 300
    size_limit = 1000
    time_limit = 10
    message_type = "custom-graph"

    def __init__(self, process_factory=None, create_time=time.time):
        super(CustomGraphPlugin, self).__init__(process_factory)
        self._create_time = create_time
        self._data = {}
        self.do_send = True

    def register(self, registry):
        super(CustomGraphPlugin, self).register(registry)
        registry.register_message(
            "custom-graph-add", self._handle_custom_graph_add)
        registry.register_message(
            "custom-graph-remove", self._handle_custom_graph_remove)
        self._persist = StoreProxy(self.registry.store)
        self._accumulate = Accumulator(self._persist, self.run_interval)

    def _handle_custom_graph_remove(self, message):
        """
        Handle remove custom-graph operation, deleting the custom graph scripts
        if found.
        """
        graph_id = int(message["graph-id"])
        graph = self.registry.store.get_graph(graph_id)
        if graph:
            filename = graph[1]
            os.unlink(filename)

        self.registry.store.remove_graph(graph_id)
        if graph_id in self._data:
            del self._data[graph_id]

    def _handle_custom_graph_add(self, message):
        """
        Handle add custom-graph operation, which can also update an existing
        custom graph script.
        """
        user = message["username"]
        shell = message["interpreter"]
        code = message["code"]
        graph_id = int(message["graph-id"])

        data_path = self.registry.config.data_path
        scripts_directory = os.path.join(data_path, "custom-graph-scripts")
        filename = os.path.join(
            scripts_directory, "graph-%d" % (graph_id,))

        if os.path.exists(filename):
            os.unlink(filename)

        try:
            uid, gid = get_user_info(user)[:2]
        except UnknownUserError:
            logging.error(u"Attempt to add graph with unknown user %s" %
                          user)
        else:
            script_file = open(filename, "wb")
            # file is closed in write_script_file
            self.write_script_file(
                script_file, filename, shell, code, uid, gid)
            if graph_id in self._data:
                del self._data[graph_id]
        self.registry.store.add_graph(graph_id, filename, user)

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e.args[0])

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted(
            self.message_type, self.send_message, urgent)

    def send_message(self, urgent):
        if not self.do_send:
            return
        self.do_send = False
        graphs = list(self.registry.store.get_graphs())
        for graph_id, filename, user in graphs:
            if graph_id not in self._data:
                if os.path.isfile(filename):
                    script_hash = self._get_script_hash(filename)
                    self._data[graph_id] = {
                        "values": [], "error": u"", "script-hash": script_hash}

        message = {"type": self.message_type, "data": self._data}

        new_data = {}
        for graph_id, item in iteritems(self._data):
            script_hash = item["script-hash"]
            new_data[graph_id] = {
                "values": [], "error": u"", "script-hash": script_hash}
        self._data = new_data

        self.registry.broker.send_message(message, self._session_id,
                                          urgent=urgent)

    def _handle_data(self, output, graph_id, now):
        if graph_id not in self._data:
            return
        try:
            data = float(output)
        except ValueError:
            if output:
                raise InvalidFormatError(output)
            else:
                raise NoOutputError()

        step_data = self._accumulate(now, data, graph_id)
        if step_data:
            self._data[graph_id]["values"].append(step_data)

    def _handle_error(self, failure, graph_id):
        if graph_id not in self._data:
            return
        if failure.check(ProcessFailedError):
            failure_value = failure.value.data
            if failure.value.exit_code:
                failure_value = ("%s (process exited with code %d)" %
                                 (failure_value, failure.value.exit_code))
            self._data[graph_id]["error"] = failure_value
        elif failure.check(ProcessTimeLimitReachedError):
            self._data[graph_id]["error"] = (
                u"Process exceeded the %d seconds limit" % (self.time_limit,))
        else:
            self._data[graph_id]["error"] = self._format_exception(
                failure.value)

    def _get_script_hash(self, filename):
        with open(filename) as file_object:
            script_content = file_object.read()
        return generate_script_hash(script_content)

    def run(self):
        """
        Iterate all the custom graphs stored and then execute each script and
        handle the output.
        """
        self.do_send = True
        graphs = list(self.registry.store.get_graphs())

        if not graphs:
            # Shortcut to prevent useless call to call_if_accepted
            return succeed([])

        return self.registry.broker.call_if_accepted(
            self.message_type, self._continue_run, graphs)

    def _continue_run(self, graphs):
        deferred_list = []
        now = int(self._create_time())

        for graph_id, filename, user in graphs:
            if os.path.isfile(filename):
                script_hash = self._get_script_hash(filename)
            else:
                script_hash = b""
            if graph_id not in self._data:
                self._data[graph_id] = {
                    "values": [], "error": u"", "script-hash": script_hash}
            else:
                self._data[graph_id]["script-hash"] = script_hash
            try:
                uid, gid, path = get_user_info(user)
            except UnknownUserError as e:
                d = fail(e)
                d.addErrback(self._handle_error, graph_id)
                deferred_list.append(d)
                continue
            if not self.is_user_allowed(user):
                d = fail(ProhibitedUserError(user))
                d.addErrback(self._handle_error, graph_id)
                deferred_list.append(d)
                continue
            if not os.path.isfile(filename):
                continue
            result = self._run_script(
                filename, uid, gid, path, {}, self.time_limit)
            result.addCallback(self._handle_data, graph_id, now)
            result.addErrback(self._handle_error, graph_id)
            deferred_list.append(result)
        return DeferredList(deferred_list)
