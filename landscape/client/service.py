import logging
import signal

from twisted.application.service import Application, Service
from twisted.application.app import startApplication

from landscape.lib.logging import rotate_logs
from landscape.client.reactor import LandscapeReactor
from landscape.client.deployment import get_versioned_persist, init_logging


class LandscapeService(Service, object):
    """Utility superclass for defining Landscape services.

    This sets up the reactor and L{Persist} object.

    @cvar service_name: The lower-case name of the service. This is used to
        generate the bpickle and the Unix socket filenames.
    @ivar config: A L{Configuration} object.
    @ivar reactor: A L{LandscapeReactor} object.
    @ivar persist: A L{Persist} object, if C{persist_filename} is defined.
    @ivar factory: A L{LandscapeComponentProtocolFactory}, it must be provided
        by instances of sub-classes.
    """
    reactor_factory = LandscapeReactor
    persist_filename = None

    def __init__(self, config):
        self.config = config
        self.reactor = self.reactor_factory()
        if self.persist_filename:
            self.persist = get_versioned_persist(self)
        if not (self.config is not None and self.config.ignore_sigusr1):
            from twisted.internet import reactor
            signal.signal(
                signal.SIGUSR1,
                lambda signal, frame: reactor.callFromThread(rotate_logs))

    def startService(self):
        Service.startService(self)
        logging.info("%s started with config %s" % (
            self.service_name.capitalize(), self.config.get_config_filename()))

    def stopService(self):
        # We don't need to call port.stopListening(), because the reactor
        # shutdown sequence will do that for us.
        Service.stopService(self)
        logging.info("%s stopped with config %s" % (
            self.service_name.capitalize(), self.config.get_config_filename()))


def run_landscape_service(configuration_class, service_class, args):
    """Run a Landscape service.

    This function instantiates the specified L{LandscapeService} subclass and
    attaches the resulting service object to a Twisted C{Application}.  After
    that it starts the Twisted L{Application} and calls the
    L{LandscapeReactor.run} method of the L{LandscapeService}'s reactor.

    @param configuration_class: The service-specific subclass of
        L{Configuration} used to parse C{args} and build the C{service_class}
        object.
    @param service_class: The L{LandscapeService} subclass to create and start.
    @param args: Command line arguments used to initialize the configuration.
    """
    # Let's consider adding this:
    # from twisted.python.log import (
    #     startLoggingWithObserver, PythonLoggingObserver)
    # startLoggingWithObserver(PythonLoggingObserver().emit, setStdout=False)

    configuration = configuration_class()
    configuration.load(args)
    init_logging(configuration, service_class.service_name)
    application = Application("landscape-%s" % (service_class.service_name,))
    service = service_class(configuration)
    service.setServiceParent(application)

    if configuration.clones > 0:

        # Increase the timeout of AMP's MethodCalls
        # XXX: we should find a better way to expose this knot, and
        # not set it globally on the class
        from landscape.lib.amp import MethodCallSender
        MethodCallSender.timeout = 300

        # Create clones here because LandscapeReactor.__init__ would otherwise
        # cancel all scheduled delayed calls
        clones = []
        for i in range(configuration.clones):
            clone_config = configuration.clone()
            clone_config.computer_title += " Clone %d" % i
            clone_config.master_data_path = configuration.data_path
            clone_config.data_path += "-clone-%d" % i
            clone_config.log_dir += "-clone-%d" % i
            clone_config.is_clone = True
            clones.append(service_class(clone_config))

        configuration.is_clone = False

        def start_clones():
            # Spawn instances over the given time window
            start_clones_over = float(configuration.start_clones_over)
            delay = start_clones_over / configuration.clones

            for i, clone in enumerate(clones):

                def start(clone):
                    clone.setServiceParent(application)
                    clone.reactor.fire("run")

                service.reactor.call_later(delay * (i + 1), start, clone=clone)

        service.reactor.call_when_running(start_clones)

    startApplication(application, False)
    if configuration.ignore_sigint:
        signal.signal(signal.SIGINT, signal.SIG_IGN)

    service.reactor.run()
