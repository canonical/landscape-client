"""Deployment code for the player."""

from landscape.service import run_landscape_service
from landscape.broker.config import BrokerConfiguration
from landscape.broker.service import BrokerService
from landscape.player.player import PayloadPlayer
from landscape.player.reader import PayloadReader


class PlaybackService(BrokerService):
    service_name = "player"

    def __init__(self, config):
        """
        @param config: A L{BrokerConfiguration}.
        """
        # Disable recording while in playback mode.
        config.record = False
        super(PlaybackService, self).__init__(config)

        self.payload_reader = PayloadReader(config.record_directory)
        self.player = PayloadPlayer(self.payload_reader, self.exchanger, 1)

    def startService(self):
        """Start the broker.

        Start the L{MessageExchange}, L{Pinger} and L{Player} services.
        """
        self.exchanger.start()
        self.pinger.start()
        self.player.load()
        self.player.play()


def run(args):
    """Run the application, given some command line arguments."""
    run_landscape_service(BrokerConfiguration, PlaybackService, args)
