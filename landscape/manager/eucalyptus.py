import os
import logging

from landscape.manager.manager import ManagerPlugin


class EucalyptusInfo(object):

    def __init__(self, tools):
        self._tools = tools

    def get_walrus_info(self):
        return self._tools._runTool("euca_conf", ["--list-walruses"])

    def get_cluster_controller_info(self):
        return self._tools._runTool("euca_conf", ["--list-clusters"])

    def get_storage_controller_info(self):
        return self._tools._runTool("euca_conf", ["--list-scs"])

    def get_node_info(self):
        return self._tools._runTool("euca_conf", ["--list-nodes"])


class EucalyptusCloudManager(ManagerPlugin):
    """A management plugin for a Eucalyptus cloud."""

    plugin_name = "eucalyptus-manager"
    message_type = "eucalyptus-info"
    run_interval = 3600

    def run(self):
        """Run the plugin.

        A C{ServiceHub} runs services that provide information about
        Eucalyptus.  If a service hub can't be created the plugin assumes that
        Eucalyptus is not installed.  In such cases a message is written to
        the log and the plugin is disabled.

        @return: A C{Deferred} that will fire when the plugin has finished
            running.
        """
        try:
            service_hub = self._start_service_hub()
        except:
            self.registry.remove(self)
            logging.info("Couldn't start service hub.  '%s' plugin has been "
                         "disabled." % self.message_type)
        else:
            deferred = service_hub.addTask(GetEucaInfo("admin"))
            deferred.addCallback(self._get_message)
            deferred.addErrback(self._get_error_message)
            deferred.addCallback(self.registry.broker.send_message)
            deferred.addBoth(lambda ignored: service_hub.stop())
            return deferred

    def _start_service_hub(self):
        """Create and start a C{ServiceHub} to use when getting credentials.

        @return: A running C{ServiceHub} with a C{EucaService} service that
            can be used to retrieve credentials.
        """
        from twisted.internet import reactor
        from imagestore.lib.service import ServiceHub
        from imagestore.eucaservice import EucaService

        data_path = self.registry.config.data_path
        base_path = os.path.join(data_path, "eucalyptus")
        service_hub = ServiceHub()
        service_hub.addService(EucaService(reactor, base_path))
        service_hub.start()
        return service_hub

    def _get_message(self, credentials):
        """Create a message with information about a Eucalyptus cloud.

        @param credentials: A C{EucaInfo} instance containing credentials for
            the Eucalyptus cloud being managed.
        @return: A message with information about Eucalyptus to send to the
            server.
        """
        from imagestore.eucaservice import EucaTools

        tools = EucaTools(credentials)
        info = EucalyptusInfo(tools)
        walrus_info = info.get_walrus_info()
        cluster_controller_info = info.get_cluster_controller_info()
        storage_controller_info = info.get_storage_controller_info()
        data = {"access_key": credentials.accessKey,
                "secret_key": credentials.secretKey,
                "private_key_path": credentials.privateKeyPath,
                "certificate_path": credentials.certificatePath,
                "cloud_certificate_path": credentials.cloudCertificatePath,
                "url_for_s3": credentials.urlForS3,
                "url_for_ec2": credentials.urlForEC2}
        return {"type": self.message_type, "credentials": data,
                "walrus_info": walrus_info,
                "cluster_controller_info": cluster_controller_info,
                "storage_controller_info": storage_controller_info}

    def _get_error_message(self, failure):
        """Create an error message.

        @param failure: A C{Failure} instance containing information about an
            error that occurred while trying to retrieve credentials.
        @return: An errir message to send to the server.
        """
        error = failure.getBriefTraceback()
        return {"type": self.message_type, "error": error}
