import os

from landscape.tests.helpers import LandscapeTest
from landscape.ui.tests.helpers import FakeGSettings
from landscape.ui.model.configuration.uisettings import ObservableUISettings



class ObservableUISettingsTest(LandscapeTest):


    default_data = {"is-hosted": True,
                    "hosted-landscape-host": "landscape.canonical.com",
                    "hosted-account-name": "Sparklehorse",
                    "hosted-password": "Vivadixiesubmarinetransmissionplot",
                    "local-landscape-host": "the.local.machine",
                    "local-account-name": "CrazyHorse",
                    "local-password": "RustNeverSleeps"
                    }

    def test_setup(self):
        """
        Test that the L{GSettings.Client} is correctly initialised.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertTrue(settings.was_called_with_args(
                "new", ObservableUISettings.BASE_KEY))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::is-hosted", uisettings._on_is_hosted_changed))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::hosted-landscape-host",
                uisettings._on_hosted_landscape_host_changed))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::hosted-account-name",
                uisettings._on_hosted_account_name_changed))
        self.assertTrue(settings.was_called_with_args(
                "connect",
                "changed::hosted-password",
                uisettings._on_hosted_password_changed))

    def test_get_is_hosted(self):
        """
        Test that the L{get_is_hosted} value is correctly fetched from the
        L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertTrue(uisettings.get_is_hosted())

    def test_set_is_hosted(self):
        """
        Test that we can correctly use L{set_is_hosted} to write the
        L{is_hosted} value to the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertTrue(uisettings.get_is_hosted())
        uisettings.set_is_hosted(False)
        self.assertFalse(uisettings.get_is_hosted())
        self.assertTrue(settings.was_called_with_args(
                "set_boolean", "is-hosted", False))

    def test_get_hosted_landscape_host(self):
        """
        Test that the L{get_hosted_landscape_host} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("landscape.canonical.com", 
                         uisettings.get_hosted_landscape_host())

    # NOTE: There is no facility to set the hosted-landscape-host

    def test_get_hosted_account_name(self):
        """
        Test that the L{get_hosted_account_name} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("Sparklehorse", 
                         uisettings.get_hosted_account_name())

    def test_set_hosted_account_name(self):
        """
        Test that L{set_hosted_account_name} correctly sets the value of
        L{hosted_account_name} in the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("Sparklehorse", uisettings.get_hosted_account_name())
        uisettings.set_hosted_account_name("Bang")
        self.assertEqual("Bang", uisettings.get_hosted_account_name())


    def test_get_hosted_password(self):
        """
        Test that the L{get_hosted_password} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("Vivadixiesubmarinetransmissionplot", 
                         uisettings.get_hosted_password())

    def test_set_hosted_password(self):
        """
        Test that L{set_hosted_password} correctly sets the value of
        L{hosted_password} in the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("Vivadixiesubmarinetransmissionplot",
                         uisettings.get_hosted_password())
        uisettings.set_hosted_password("Bang")
        self.assertEqual("Bang", uisettings.get_hosted_password())

    def test_get_local_landscape_host(self):
        """
        Test that the L{get_local_landscape_host} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("the.local.machine", 
                         uisettings.get_local_landscape_host())

    def test_set_local_landscape_host(self):
        """
        Test that L{set_local_landscape_host} correctly sets the value of
        L{local_landscape_host} in the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("the.local.machine",
                         uisettings.get_local_landscape_host())
        uisettings.set_local_landscape_host("Bang")
        self.assertEqual("Bang", uisettings.get_local_landscape_host())
        
    def test_get_local_account_name(self):
        """
        Test that the L{get_local_account_name} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("CrazyHorse", 
                         uisettings.get_local_account_name())

    def test_set_local_account_name(self):
        """
        Test that L{set_local_account_name} correctly sets the value of
        L{local_account_name} in the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("CrazyHorse",
                         uisettings.get_local_account_name())
        uisettings.set_local_account_name("Bang")
        self.assertEqual("Bang", uisettings.get_local_account_name())

    def test_get_local_password(self):
        """
        Test that the L{get_local_password} value is correctly fetched
        from the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("RustNeverSleeps", 
                         uisettings.get_local_password())

    def test_set_local_password(self):
        """
        Test that L{set_local_password} correctly sets the value of
        L{local_password} in the L{GSettings.Client}.
        """
        settings = FakeGSettings(data=self.default_data)
        uisettings = ObservableUISettings(settings)
        self.assertEqual("RustNeverSleeps",
                         uisettings.get_local_password())
        uisettings.set_local_password("Bang")
        self.assertEqual("Bang", uisettings.get_local_password())
        
