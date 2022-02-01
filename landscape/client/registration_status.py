import os
import sys

from landscape.client.broker.config import BrokerConfiguration
from landscape.client.configuration import get_client_identity


def registration_status_string(args=sys.argv):
    '''
    A simple output displaying whether the client is registered or not, the
    account name, and config and data paths
    '''

    config = BrokerConfiguration()
    config.load(args)
    config_path = os.path.abspath(config._config_filename)

    identity = get_client_identity(config)

    is_registered = bool(identity.secure_id)

    text_lines = []
    text_lines.append('Registered:    {}'.format(is_registered))
    text_lines.append('Config Path:   {}'.format(config_path))
    text_lines.append('Data Path      {}'.format(config.data_path))
    if is_registered:
        text_lines.append('Account Name:  {}'.format(identity.account_name))

    return '\n'.join(text_lines)


def display_registration_status():
    print(registration_status_string())
