from landscape.client.broker.tests.helpers import BrokerConfigurationHelper
from landscape.client.broker.registration import Identity
from landscape.client.registration_status import registration_status_string
from landscape.client.tests.helpers import LandscapeTest


class RegistrationStatusTest(LandscapeTest):

    helpers = [BrokerConfigurationHelper]

    def setUp(self):
        super(RegistrationStatusTest, self).setUp()
        self.custom_args = ['hello.py']  # Fake python script name
        self.account_name = 'world'
        self.data_path = '/tmp/registrationtest'
        self.config_text = ('[client]\ncomputer_title = hello\n'
                            'account_name = {}\ndata_path = {}')\
            .format(self.account_name, self.data_path)

    def test_not_registered(self):
        '''Default state is when secure ID is not set'''
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        status = registration_status_string(args=self.custom_args)
        self.assertIn('False', status)
        self.assertNotIn(self.account_name, status)

    def test_registered(self):
        '''
        When secure ID is set, then the status should display as True and
        account name should be present
        '''
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        Identity.secure_id = 'test'  # Simulate successful registration
        status = registration_status_string(args=self.custom_args)
        self.assertIn('True', status)
        self.assertIn(self.account_name, status)

    def test_custom_config_path(self):
        '''The custom config path should show up in the status'''
        custom_path = self.makeFile(self.config_text)
        self.custom_args += ['-c', custom_path]
        status = registration_status_string(args=self.custom_args)
        self.assertIn(custom_path, status)

    def test_data_path(self):
        '''The config data path should show in the status'''
        config_filename = self.config.default_config_filenames[0]
        self.makeFile(self.config_text, path=config_filename)
        status = registration_status_string(args=self.custom_args)
        self.assertIn(self.data_path, status)
