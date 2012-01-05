from landscape.configuration import LandscapeSetupConfiguration


class SettingsConfiguration(LandscapeSetupConfiguration):
    required_options = []

    def __init__(self):
        super(SettingsConfiguration, self).__init__(None)
