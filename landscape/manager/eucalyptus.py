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

    def get_node_controller_info(self):
        return self._tools._runTool("euca_conf", ["--list-nodes"])


class EucalyptusCloudManager(ManagerPlugin):
    """A management plugin for a Eucalyptus cloud."""

    plugin_name = "eucalyptus-manager"
    message_type = "eucalyptus-info"
    run_interval = 3600

    def __init__(self, service_hub_factory=None, eucalyptus_info_factory=None):
        super(EucalyptusCloudManager, self).__init__()
        self._service_hub_factory = service_hub_factory
        if self._service_hub_factory is None:
            self._service_hub_factory = start_service_hub
        self._eucalyptus_info_factory = eucalyptus_info_factory
        if self._eucalyptus_info_factory is None:
            self._eucalyptus_info_factory = get_eucalyptus_info

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
            data_path = self.registry.config.data_path
            service_hub = self._service_hub_factory(data_path)
        except:
            self.registry.remove(self)
            logging.info("Couldn't start service hub.  '%s' plugin has been "
                         "disabled." % self.message_type)
        else:
            from imagestore.eucaservice import GetEucaInfo

            deferred = service_hub.addTask(GetEucaInfo("admin"))
            deferred.addCallback(self._get_message)
            deferred.addErrback(self._get_error_message)
            deferred.addCallback(self.registry.broker.send_message)
            deferred.addBoth(lambda ignored: service_hub.stop())
            return deferred

    def _get_message(self, credentials):
        """Create a message with information about a Eucalyptus cloud.

        @param credentials: A C{EucaInfo} instance containing credentials for
            the Eucalyptus cloud being managed.
        @return: A message with information about Eucalyptus to send to the
            server.
        """
        info = self._eucalyptus_info_factory(credentials)
        walrus_info = info.get_walrus_info()
        cluster_controller_info = info.get_cluster_controller_info()
        storage_controller_info = info.get_storage_controller_info()
        node_controller_info = info.get_node_controller_info()
        data = {"access_key": credentials.accessKey,
                "secret_key": credentials.secretKey,
                "private_key_path": credentials.privateKeyPath,
                "certificate_path": credentials.certificatePath,
                "cloud_certificate_path": credentials.cloudCertificatePath,
                "url_for_s3": credentials.urlForS3,
                "url_for_ec2": credentials.urlForEC2}
        return {"type": self.message_type, "basic_info": data,
                "walrus_info": walrus_info,
                "cluster_controller_info": cluster_controller_info,
                "storage_controller_info": storage_controller_info,
                "node_controller_info": node_controller_info}

    def _get_error_message(self, failure):
        """Create an error message.

        @param failure: A C{Failure} instance containing information about an
            error that occurred while trying to retrieve credentials.
        @return: An errir message to send to the server.
        """
        error = failure.getBriefTraceback()
        return {"type": self.message_type, "error": error}


def start_service_hub(self, data_path):
    """Create and start a C{ServiceHub} to use when getting credentials.

    @param data_path: The path to Landscape's data directory.
    @return: A running C{ServiceHub} with a C{EucaService} service that
        can be used to retrieve credentials.
    """
    from twisted.internet import reactor
    from imagestore.lib.service import ServiceHub
    from imagestore.eucaservice import EucaService

    base_path = os.path.join(data_path, "eucalyptus")
    service_hub = ServiceHub()
    service_hub.addService(EucaService(reactor, base_path))
    service_hub.start()
    return service_hub


def get_eucalyptus_info(self, credentials):
    """Create a L{EucalyptusInfo} instance.

    @param credentials: An C{imagestore.eucaservice.EucaInfo} instance.
    @return: A L{EucalyptusInfo} instance.
    """
    from imagestore.eucaservice import EucaTools
    return EucalyptusInfo(EucaTools(credentials))
