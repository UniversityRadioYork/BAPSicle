from helpers.logging_manager import LoggingManager
import json
import os
import logging
import time
from datetime import datetime
from copy import copy
from helpers.os_environment import resolve_external_file_path


class StateManager:
    filepath = None
    logger = None
    __state = {}
    __state_in_file = {}
    # Dict of times that params can be updated after, if the time is before current time, it can be written immediately.
    __rate_limit_params_until = {}
    __rate_limit_period_s = 0


    def __init__(self, name, logger: LoggingManager, default_state=None, rate_limit_params=[], rate_limit_period_s = 5):
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
            self.state = copy(default_state)
            self.__state_in_file = copy(self.state)
        else:
            try:
                self.__state = json.loads(file_state)
            except:
                self._logException("Failed to parse state JSON. Resetting to default state.")
                self.state = default_state

        # Now setup the rate limiting
        # Essentially rate limit all values to "now" to start with, allowing the first update
        # of all vars to succeed.
        for param in rate_limit_params:
            self.__rate_limit_params_until[param] = self._currentTimeS
        self.__rate_limit_period_s = rate_limit_period_s

    @property
    def state(self):
        return copy(self.__state)

    @state.setter
    def state(self, state):
        self.__state = copy(state)

    def write_to_file(self,state):
        if self.__state_in_file == state:
            # No change to be updated.
            return

        self.__state_in_file = state

        # Make sure we're not manipulating state
        state = copy(state)

        now = datetime.now()

        current_time = now.strftime("%H:%M:%S")
        state["last_updated"] = current_time
        try:
            state_json = json.dumps(state, indent=2, sort_keys=True)
        except:
            self._logException("Failed to dump JSON state.")
        else:
            with open(self.filepath, "w") as file:

                file.write(state_json)

    def update(self, key, value):
        update_file = True
        if (key in self.__rate_limit_params_until.keys()):
            # The key we're trying to update is expected to be updating very often,
            # We're therefore going to check before saving it.
            if self.__rate_limit_params_until[key] > self._currentTimeS:
                update_file = False
            else:
                self.__rate_limit_params_until[key] = self._currentTimeS + self.__rate_limit_period_s


        state_to_update = self.state

        if state_to_update[key] == value:
            # We're trying to update the state with the same value.
            # In this case, ignore the update
            return

        state_to_update[key] = value

        self.state = state_to_update

        if (update_file == True):
            self.write_to_file(state_to_update)

    def _log(self, text, level=logging.INFO):
        self.logger.log.log(level, "State Manager: " + text)

    def _logException(self, text):
        self.logger.log.exception("State Manager: " + text)

    @property
    def _currentTimeS(self):
        return time.time()
