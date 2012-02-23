class UISettings(object):

    BASE_KEY = "com.canonical.landscape-client-settings"

    def __init__(self, settings):
        self.settings = settings.new(self.BASE_KEY)

    def get_is_hosted(self):
        return self.settings.get_boolean("is-hosted")

    def set_is_hosted(self, value):
        self.settings.set_boolean("is-hosted", value)

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

    def _on_is_hosted_changed(self, settings, key):
        pass

    def _on_hosted_landscape_host_changed(self, settings, key):
        pass

    def _on_hosted_account_name_changed(self, settings, key):
        pass

    def _on_hosted_password_changed(self, settings, key):
        pass

    def _on_local_landscape_host_changed(self, settings, key):
        pass

    def _on_local_account_name_changed(self, settings, key):
        pass

    def _on_local_password_changed(self, settings, key):
        pass
