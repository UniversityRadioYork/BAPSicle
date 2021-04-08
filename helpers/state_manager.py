import json
import os
from logging import CRITICAL, INFO
import time
from datetime import datetime
from copy import copy
from typing import Any, List

from plan import PlanItem
from helpers.logging_manager import LoggingManager
from helpers.os_environment import resolve_external_file_path


class StateManager:
    filepath: str
    logger: LoggingManager
    callbacks: List[Any] = []
    __state = {}
    __state_in_file = {}
    # Dict of times that params can be updated after, if the time is before current time, it can be written immediately.
    __rate_limit_params_until = {}
    __rate_limit_period_s = 0

    def __init__(
        self,
        name,
        logger: LoggingManager,
        default_state=None,
        rate_limit_params=[],
        rate_limit_period_s=5,
    ):
        self.logger = logger

        self.filepath = resolve_external_file_path("/state/" + name + ".json")
        self._log("State file path set to: " + self.filepath)

        if not os.path.isfile(self.filepath):
            self._log("No existing state file found.")
            try:
                # Try creating the file.
                open(self.filepath, "x")
            except Exception:
                self._log("Failed to create state file.", CRITICAL)
                return

        with open(self.filepath, "r") as file:
            file_state = file.read()

        if file_state == "":
            self._log("State file is empty. Setting default state.")
            self.state = default_state
            self.__state_in_file = copy(self.state)
        else:
            try:
                file_state = json.loads(file_state)

                # Turn from JSON -> PlanItem
                if "channel" in file_state:
                    file_state["loaded_item"] = (
                        PlanItem(file_state["loaded_item"])
                        if file_state["loaded_item"]
                        else None
                    )
                    file_state["show_plan"] = [
                        PlanItem(obj) for obj in file_state["show_plan"]
                    ]

                # Now feed the loaded state into the initialised state manager.
                self.state = file_state
            except Exception:
                self._logException(
                    "Failed to parse state JSON. Resetting to default state."
                )
                self.state = default_state
                self.__state_in_file = copy(self.state)

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

    def write_to_file(self, state):
        if self.__state_in_file == state:
            # No change to be updated.
            return

        self.__state_in_file = state

        # Make sure we're not manipulating state
        state_to_json = copy(state)

        now = datetime.now()

        current_time = now.strftime("%H:%M:%S")
        state_to_json["last_updated"] = current_time

        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        if "channel" in state_to_json:  # If its a channel object
            state_to_json["loaded_item"] = (
                state_to_json["loaded_item"].__dict__
                if state_to_json["loaded_item"]
                else None
            )
            state_to_json["show_plan"] = [
                repr.__dict__ for repr in state_to_json["show_plan"]
            ]
        try:
            state_json = json.dumps(state_to_json, indent=2, sort_keys=True)
        except Exception:
            self._logException("Failed to dump JSON state.")
        else:
            with open(self.filepath, "w") as file:
                file.write(state_json)

    def update(self, key: str, value: Any, index: int = -1):
        update_file = True
        if key in self.__rate_limit_params_until.keys():
            # The key we're trying to update is expected to be updating very often,
            # We're therefore going to check before saving it.
            if self.__rate_limit_params_until[key] > self._currentTimeS:
                update_file = False
            else:
                self.__rate_limit_params_until[key] = (
                    self._currentTimeS + self.__rate_limit_period_s
                )

        state_to_update = self.state

        if key in state_to_update and index == -1 and state_to_update[key] == value:
            # We're trying to update the state with the same value.
            # In this case, ignore the update
            return

        if index > -1 and key in state_to_update:
            if not isinstance(state_to_update[key], list):
                return
            list_items = state_to_update[key]
            if index >= len(list_items):
                return
            list_items[index] = value
            state_to_update[key] = list_items
        else:
            state_to_update[key] = value

        self.state = state_to_update

        if update_file:
            # Either a routine write, or state has changed.
            # Update the file
            self.write_to_file(state_to_update)
            # Now tell any callback functions.
            for callback in self.callbacks:
                try:
                    callback()
                except Exception as e:
                    self.logger.log.critical(
                        "Failed to execute status callback: {}".format(e)
                    )

    def add_callback(self, function):
        self._log("Adding callback: {}".format(str(function)))
        self.callbacks.append(function)

    def _log(self, text: str, level: int = INFO):
        self.logger.log.log(level, "State Manager: " + text)

    def _logException(self, text: str):
        self.logger.log.exception("State Manager: " + text)

    @property
    def _currentTimeS(self):
        return time.time()
