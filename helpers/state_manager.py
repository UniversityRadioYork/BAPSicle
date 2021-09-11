import json
import os
from logging import DEBUG, INFO
import time
from datetime import datetime
from copy import copy
from typing import Any, Dict, List

from baps_types.plan import PlanItem
from helpers.logging_manager import LoggingManager
from helpers.os_environment import resolve_external_file_path


class StateManager:
    filepath: str
    logger: LoggingManager
    callbacks: List[Any] = []
    __state = {}
    # Dict of times that params can be updated after, if the time is before current time, it can be written immediately.
    __rate_limit_params_until = {}
    __rate_limit_period_s = 0

    def __init__(
        self,
        name,
        logger: LoggingManager,
        default_state: Dict[str, Any] = None,
        rate_limit_params=[],
        rate_limit_period_s=5,
    ):
        self.logger = logger

        path_dir: str = resolve_external_file_path("/state")
        if not os.path.isdir(path_dir):
            try:
                # Try creating the directory.
                os.mkdir(path_dir)
            except Exception:
                self._logException("Failed to create state directory.")
                return

        self.filepath = resolve_external_file_path("/state/" + name + ".json")
        self._log("State file path set to: " + self.filepath)

        if not os.path.isfile(self.filepath):
            self._log("No existing state file found.")
            try:
                # Try creating the file.
                open(self.filepath, "x")
            except Exception:
                self._logException("Failed to create state file.")
                return

        file_raw: str
        with open(self.filepath, "r") as file:
            file_raw = file.read()

        if file_raw == "":
            self._log("State file is empty. Setting default state.")
            self.state = default_state
        else:
            try:
                file_state: Dict[str, Any] = json.loads(file_raw)

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

                # If there are any new config options in the default state, save them.
                # Uses update() to save them to file too.
                for key in default_state.keys():
                    if key not in file_state.keys():
                        self.update(key, default_state[key])

            except Exception:
                self._logException(
                    "Failed to parse state JSON. Resetting to default state."
                )
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

    # Useful for pipeproxy, since it can't read attributes direct.
    def get(self):
        return self.state

    @state.setter
    def state(self, state):
        self.__state = copy(state)

    def write_to_file(self, state):

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
            allow = False

            # It's hard to compare lists, especially of complex objects like show plans, just write it.
            if isinstance(value, list):
                allow = True

            # If the two objects have dict representations, and they don't match, allow writing.
            # TODO: This should be easier.
            if getattr(value, "__dict__", None) and getattr(
                state_to_update[key], "__dict__", None
            ):
                if value.__dict__ != state_to_update[key].__dict__:
                    allow = True

            if not allow:

                # Just some debug logging.
                if update_file and (
                    key
                    not in ["playing", "loaded", "initialised", "remaining", "pos_true"]
                ):
                    self._log(
                        "Not updating state for key '{}' with value '{}' of type '{}'.".format(
                            key, value, type(value)
                        ),
                        DEBUG,
                    )

                # We're trying to update the state with the same value.
                # In this case, ignore the update
                # This happens to reduce spam on file writes / callbacks fired when update_file is true.
                return

        if index > -1 and key in state_to_update:
            if not isinstance(state_to_update[key], list):
                self._log(
                    "Not updating state for key '{}' with value '{}' of type '{}' since index is set and key is not a list.".format(
                        key, value, type(value)
                    ),
                    DEBUG,
                )
                return
            list_items = state_to_update[key]
            if index >= len(list_items):
                self._log(
                    "Not updating state for key '{}' with value '{}' of type '{}' because index '{}' is too large..".format(
                        key, value, type(value), index
                    ),
                    DEBUG,
                )
                return
            list_items[index] = value
            state_to_update[key] = list_items
        else:
            state_to_update[key] = value

        self.state = state_to_update

        if update_file:
            self._log(
                "Writing change to key '{}' with value '{}' of type '{}' to disk.".format(
                    key, value, type(value)
                ),
                DEBUG,
            )
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
