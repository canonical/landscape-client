import os
import logging

from landscape.lib.compat import SafeConfigParser
from landscape.client.monitor.plugin import MonitorPlugin


class UpdateManager(MonitorPlugin):
    """
    Report on changes to the update-manager configuration.

    @param update_manager_filename: the path to the update-manager
        configuration file.
    """

    # This file is used by the update-manager and may contain a "Prompt"
    # variable which indicates that users are prompted to upgrade the release
    # when any new release is available ("normal"); when a new LTS release is
    # available ("lts"); or never ("never").
    update_manager_filename = "/etc/update-manager/release-upgrades"

    persist_name = "update-manager"
    scope = "package"
    run_interval = 3600  # 1 hour
    run_immediately = True

    def __init__(self, update_manager_filename=None):
        if update_manager_filename is not None:
            self.update_manager_filename = update_manager_filename

    def _get_prompt(self):
        """
        Retrieve the update-manager upgrade prompt which dictates when we
        should prompt users to upgrade the release.  Current valid values are
        "normal" (prompt on all the availability of all releases), "lts"
        (prompt only when LTS releases are available), and "never".
        """
        if not os.path.exists(self.update_manager_filename):
            # There is no config, so we just act as if it's set to 'normal'
            return "normal"
        config_file = open(self.update_manager_filename)
        parser = SafeConfigParser()
        parser.readfp(config_file)
        prompt = parser.get("DEFAULT", "Prompt")
        valid_prompts = ["lts", "never", "normal"]
        if prompt not in valid_prompts:
            prompt = "normal"
            message = ("%s contains invalid Prompt value. "
                       "Should be one of %s." % (
                           self.update_manager_filename,
                           valid_prompts))
            logging.warning(message)
        return prompt

    def send_message(self):
        """
        Send the current upgrade release prompt to the server.
        """
        prompt = self._get_prompt()
        if prompt == self._persist.get("prompt"):
            return
        self._persist.set("prompt", prompt)
        message = {
            "type": "update-manager-info",
            "prompt": prompt}
        logging.info("Queueing message with updated "
                     "update-manager status.")
        return self.registry.broker.send_message(message, self._session_id)

    def run(self):
        """
        Send the update-manager-info messages, if the server accepts them.
        """
        return self.registry.broker.call_if_accepted(
            "update-manager-info", self.send_message)
