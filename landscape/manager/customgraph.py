import os
import time

from twisted.internet.defer import fail, DeferredList

from landscape.lib.scriptcontent import generate_script_hash
from landscape.accumulate import Accumulator
from landscape.manager.manager import ManagerPlugin
from landscape.manager.scriptexecution import (
    ProcessAccumulationProtocol, ProcessFailedError, ScriptRunnerMixin,
    ProcessTimeLimitReachedError)


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


class CustomGraphPlugin(ManagerPlugin, ScriptRunnerMixin):
    """
    Manage adding and deleting custom graph scripts, and then run the scripts
    in a loop.
    """
    run_interval = 300
    size_limit = 1000
    time_limit = 10
    message_type = "custom-graph"

    def __init__(self, process_factory=None, create_time=time.time):
        """
        @param process_factory: The L{IReactorProcess} provider to run the
            process with.
        """
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

        script_file = file(filename, "w")
        uid, gid = self.get_pwd_infos(user)[:2]
        self.write_script_file(
            script_file, filename, shell, code, uid, gid)
        self.registry.store.add_graph(graph_id, filename, user)

        if graph_id in self._data:
            del self._data[graph_id]

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e)

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
                script_hash = self._get_script_hash(filename)
                self._data[graph_id] = {
                    "values": [], "error": u"", "script-hash": script_hash}

        message = {"type": self.message_type, "data": self._data}

        new_data = {}
        for graph_id, item in self._data.iteritems():
            script_hash = item["script-hash"]
            new_data[graph_id] = {
                "values": [], "error": u"", "script-hash": script_hash}
        self._data = new_data

        self.registry.broker.send_message(message, urgent=urgent)

    def _handle_data(self, output, graph_id, now):
        if graph_id not in self._data:
            return
        data = float(output)
        step_data = self._accumulate(now, data, graph_id)
        if step_data:
            self._data[graph_id]["values"].append(step_data)

    def _handle_error(self, failure, graph_id):
        if graph_id not in self._data:
            return
        if failure.check(ProcessFailedError):
            self._data[graph_id]["error"] = failure.value.data.decode("utf-8")
        elif failure.check(ProcessTimeLimitReachedError):
            self._data[graph_id]["error"] = (
                u"Process exceeded the %d seconds limit" % (self.time_limit,))
        else:
            self._data[graph_id]["error"] = self._format_exception(
                failure.value)

    def _get_script_hash(self, filename):
        file_object = file(filename)
        script_content = file_object.read()
        file_object.close()
        return generate_script_hash(script_content)

    def run(self):
        """
        Iterate all the custom graphs stored and then execute each script and
        handle the output.
        """
        self.do_send = True
        defferred_list = []
        graphs = list(self.registry.store.get_graphs())
        now = int(self._create_time())
        for graph_id, filename, user in graphs:
            if graph_id not in self._data:
                script_hash = self._get_script_hash(filename)
                self._data[graph_id] = {
                    "values": [], "error": u"", "script-hash": script_hash}
            if user is not None:
                if not self.is_user_allowed(user):
                    d = fail(ProcessFailedError(
                        u"Custom graph cannot be run as user %s." % (user,)))
                    d.addErrback(self._handle_error, graph_id)
                    defferred_list.append(d)
                    continue
            uid, gid, path = self.get_pwd_infos(user)
            pp = ProcessAccumulationProtocol(
                self.registry.reactor, self.size_limit)
            self.process_factory.spawnProcess(
                pp, filename, uid=uid, gid=gid, path=path)
            pp.schedule_cancel(self.time_limit)
            result = pp.result_deferred
            result.addCallback(self._handle_data, graph_id, now)
            result.addErrback(self._handle_error, graph_id)
            defferred_list.append(result)
        return DeferredList(defferred_list)
