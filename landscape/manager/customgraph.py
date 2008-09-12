import os
import pwd
import time

from twisted.internet.defer import fail, DeferredList

from landscape.manager.manager import ManagerPlugin, SUCCEEDED, FAILED

from landscape.manager.scriptexecution import (
    ALL_USERS, ProcessAccumulationProtocol, ProcessFailedError)


class CustomGraphManager(ManagerPlugin):
    """
    Manage adding and deleting custom graph scripts.
    """
    run_interval = 300
    size_limit = 1000
    time_limit = 10

    def __init__(self, process_factory=None, create_time=time.time):
        """
        @param process_factory: The L{IReactorProcess} provider to run the
            process with.
        """
        if process_factory is None:
            from twisted.internet import reactor as process_factory
        self.process_factory = process_factory
        self._create_time = create_time
        self._data = {}

    def register(self, registry):
        super(CustomGraphManager, self).register(registry)
        registry.register_message(
            "custom-graph-add", self._handle_custom_graph_add)
        registry.register_message(
            "custom-graph-remove", self._handle_custom_graph_remove)
        registry.reactor.call_every(self.run_interval, self.run)

    def _handle_custom_graph_remove(self, message):
        opid = message["operation-id"]
        graph_id = message["graph-id"]
        graph = self.registry.store.get_graph(graph_id)
        if graph:
            filename = graph[1]
            # Make it writable to be sure to be able to delete it
            os.chmod(filename, 0777)
            os.unlink(filename)

        self.registry.store.remove_graph(graph_id)
        self._respond(SUCCEEDED, "", opid)

    def _handle_custom_graph_add(self, message):
        opid = message["operation-id"]
        try:
            user = message["username"]
            allowed_users = self.registry.config.get_allowed_script_users()
            if allowed_users != ALL_USERS and user not in allowed_users:
                return self._respond(
                    FAILED,
                    u"Custom graph cannot be run as user %s." % (user,),
                    opid)

            shell = message["interpreter"]
            code = message["code"]
            graph_id = message["graph-id"]
            if not os.path.exists(shell.split()[0]):
                return self._respond(
                    FAILED,
                    u"Unknown interpreter: '%s'" % (shell,),
                    opid)

            data_path = self.registry.config.data_path
            scripts_directory = os.path.join(data_path, "custom-graph-scripts")
            if not os.path.exists(scripts_directory):
                os.makedirs(scripts_directory)
            filename = os.path.join(
                scripts_directory, "graph-%d" % (graph_id,))

            if os.path.exists(filename):
                os.chmod(filename, 0777)
                os.unlink(filename)

            script_file = file(filename, "w")
            uid = None
            gid = None
            if user is not None:
                info = pwd.getpwnam(user)
                uid = info.pw_uid
                gid = info.pw_gid
            os.chmod(filename, 0700)
            if uid is not None:
                os.chown(filename, uid, gid)
            script_file.write(
                "#!%s\n%s" % (shell.encode("utf-8"), code.encode("utf-8")))
            script_file.close()
        except Exception, e:
            self._respond(FAILED, self._format_exception(e), opid)
            raise
        else:
            self.registry.store.add_graph(graph_id, filename, user)
            return self._respond(SUCCEEDED, "", opid)

    def _format_exception(self, e):
        return u"%s: %s" % (e.__class__.__name__, e)

    def _respond(self, status, data, opid):
        message =  {"type": "operation-result",
                    "status": status,
                    "result-text": data,
                    "operation-id": opid}
        return self.registry.broker.send_message(message, True)

    def exchange(self, urgent=False):
        self.registry.broker.call_if_accepted(
            "custom-graph", self.send_message, urgent)

    def send_message(self, urgent):
        if not self._data:
            return
        message = {"type": "custom-graph", "data": self._data}
        self._data = {}
        self.registry.broker.send_message(message, urgent=urgent)

    def _handle_data(self, output, graph_id, now):
        try:
            data = float(output)
        except ValueError, e:
            self._data[graph_id]["error"] = self._format_exception(e)
        else:
            self._data[graph_id]["values"].append((now, data))

    def _handle_error(self, failure, graph_id):
        if failure.check(ProcessFailedError):
            self._data[graph_id]["error"] = failure.value.data
        else:
            self._data[graph_id]["error"] = self._format_exception(
                failure.value)

    def run(self):
        dl = []
        graphes = self.registry.store.get_graphes()
        now = int(self._create_time())
        for graph_id, filename, user in graphes:
            if graph_id not in self._data:
                self._data[graph_id] = {"values": [], "error": u""}
            uid = None
            gid = None
            path = None
            if user is not None:
                info = pwd.getpwnam(user)
                uid = info.pw_uid
                gid = info.pw_gid
                path = info.pw_dir
                if not os.path.exists(path):
                    path = "/"
                allowed_users = self.registry.config.get_allowed_script_users()
                if allowed_users != ALL_USERS and user not in allowed_users:
                    d = fail(ProcessFailedError(
                        u"Custom graph cannot be run as user %s." % (user,)))
                    d.addErrback(self._handle_error, graph_id)
                    dl.append(d)
                    continue
            pp = ProcessAccumulationProtocol(
                self.registry.reactor, self.size_limit)
            self.process_factory.spawnProcess(
                pp, filename, uid=uid, gid=gid, path=path)
            pp.schedule_cancel(self.time_limit)
            result = pp.result_deferred
            result.addCallback(self._handle_data, graph_id, now)
            result.addErrback(self._handle_error, graph_id)
            dl.append(result)
        return DeferredList(dl)
