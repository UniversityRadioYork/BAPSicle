from helpers.logging_manager import LoggingManager
import json
import os
import logging
from helpers.os_environment import resolve_external_file_path


class StateManager:
    filepath = None
    logger = None
    __state = {}

    def __init__(self, name, logger: LoggingManager, default_state=None):
        self.logger = logger

        self.filepath = resolve_external_file_path("/state/" + name + ".json")
        self._log("State file path set to: " + self.filepath)

        if not os.path.isfile(self.filepath):
            self._log("No existing state file found.")
            try:
                # Try creating the file.
                open(self.filepath, "x")
            except:
                self._log("Failed to create state file.", logging.CRITICAL)
                return

        with open(self.filepath, 'r') as file:
            file_state = file.read()

        if file_state == "":
            self._log("State file is empty. Setting default state.")
            self.state = default_state
        else:
            try:
                self.__state = json.loads(file_state)
            except:
                self._logException("Failed to parse state JSON. Resetting to default state.")
                self.state = default_state

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, state):
        self.__state = state

        try:
            state_json = json.dumps(state, indent=2, sort_keys=True)
        except:
            self._logException("Failed to dump JSON state.")
        else:
            with open(self.filepath, "w") as file:

                file.write(state_json)

    def update(self, key, value):
        state = self.state
        state[key] = value
        self.state = state

    def _log(self, text, level=logging.INFO):
        self.logger.log.log(level, "State Manager: " + text)

    def _logException(self, text):
        self.logger.log.exception("State Manager: " + text)
