from landscape.configuration import LandscapeSetupConfiguration


class LandscapeSettingsConfiguration(LandscapeSetupConfiguration):
    required_options = []

    def __init__(self):
        super(LandscapeSettingsConfiguration, self).__init__(None)
