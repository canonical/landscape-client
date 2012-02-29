class UISettings(object):
    """
    A very thin wrapper around L{GSettings} to avoid having to know the
    L{BaseKey} and type information elsewhere.  In some future version it would
    be right to bind to change events here so we can react to people changing
    the settings in dconf, for now that is overkill.
    """

    BASE_KEY = "com.canonical.landscape-client-settings"

    def __init__(self, settings):
        self.settings = settings.new(self.BASE_KEY)

    def get_management_type(self):
        return self.settings.get_string("management-type")

    def set_management_type(self, value):
        self.settings.set_string("management-type", value)

    def get_computer_title(self):
        return self.settings.get_string("computer-title")

    def set_computer_title(self, value):
        self.settings.set_string("computer-title", value)

    def get_hosted_landscape_host(self):
        return self.settings.get_string("hosted-landscape-host")

    def get_hosted_account_name(self):
        return self.settings.get_string("hosted-account-name")

    def set_hosted_account_name(self, value):
        self.settings.set_string("hosted-account-name", value)

    def get_hosted_password(self):
        return self.settings.get_string("hosted-password")

    def set_hosted_password(self, value):
        self.settings.set_string("hosted-password", value)

    def get_local_landscape_host(self):
        return self.settings.get_string("local-landscape-host")

    def set_local_landscape_host(self, value):
        self.settings.set_string("local-landscape-host", value)

    def get_local_account_name(self):
        return self.settings.get_string("local-account-name")

    def set_local_account_name(self, value):
        self.settings.set_string("local-account-name", value)

    def get_local_password(self):
        return self.settings.get_string("local-password")

    def set_local_password(self, value):
        self.settings.set_string("local-password", value)
