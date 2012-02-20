import os

from gi.repository import Gio
from lxml import etree

from landscape.tests.helpers import LandscapeTest
from landscape.ui.model.configuration.uisettings import ObservableUISettings


class FakeGSettings(object):

    calls = {}

    def __init__(self, data={}):
        self.set_data(data)
        tree = etree.parse(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../../../../../", 
                "glib-2.0/schemas/",
                "com.canonical.landscape-client-settings.gschema.xml"))
        root = tree.getroot()
        self.schema = root.find("schema")
        assert(self.schema.attrib["id"] == \
                   "com.canonical.landscape-client-settings")
        self.keys = {}
        for key in self.schema.findall("key"):
            self.keys[key.attrib["name"]] = key.attrib["type"]
        

    def check_key_data(self, name, gstype):
        if self.keys.has_key(name):
            if self.keys[name] == gstype:
                return True
            else:
                raise ValueError, "The GSchema file says %s is a %s, " + \
                    "but you asked for a %s" % (name, self.keys[name], gstype)
        else:
            raise KeyError, "Can't find %s in the GSchema file!" % name


    def get_value(self, name, gstype):
        if self.check_key_data(name, gstype):
            return self.data[name]


    def set_value(self, name, gstype, value):
        if self.check_key_data(name, gstype):
            self.data[name] = value
        
    def set_data(self, data):
        self.data = data
        
    def _call(self, name, *args):
        [count, arglist] = self.calls.get(name, (0, []))
        count += 1
        arglist.append(self._args_to_string(*args))
        self.calls[name] = [count, arglist]

    def _args_to_string(self, *args):
        return "|".join([str(arg) for arg in args])
        
    def new(self, key):
        self._call("new", key)
        return self

    def connect(self, signal, callback, *args):
        self._call("connect", signal, callback, *args)

    def get_boolean(self, name):
        self._call("get_boolean", name)
        return self.get_value(name, "b")

    def set_boolean(self, name, value):
        self._call("set_boolean", name, value)
        self.set_value(name, "b", value)
        
    def get_string(self, name):
        self._call("get_string", name)
        return self.get_value(name, "s")

    def set_string(self, name, value):
        self._call("set_string", name, value)
        self.set_value(name, "s", value)
    
    def was_called(self, name):
        return self.calls.haskey(name)

    def was_called_with_args(self, name, *args):
        try:
            [count, arglist] = self.calls.get(name, (0,[]))
        except KeyError:
            return False
        
        expected_args = self._args_to_string(*args)
        return expected_args in arglist
        

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
        
