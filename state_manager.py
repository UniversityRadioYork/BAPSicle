import copy
import json
import os
from helpers.os_environment import resolve_external_file_path
from plan import PlanObject


class StateManager:
    filepath = None
    __state = {}

    def __init__(self, name, default_state=None):
        self.filepath = resolve_external_file_path("/state/" + name + ".json")
        if not os.path.isfile(self.filepath):
            self.log("No file found for " + self.filepath)
            try:
                # Try creating the file.
                open(self.filepath, "x")
            except:
                self.log("failed to create state file")
                return

        self.log("Saving state to " + self.filepath)

        file = open(self.filepath, 'r')

        file_state = file.read()
        file.close()

        # TODO: also check for invalid JSON state
        if file_state == "":
            print("file empty")

            self.state = default_state

        else:
            self.__state = json.loads(file_state)

            # Turn from JSON -> PlanObject
            self.__state["loaded_item"] = PlanObject(self.__state["loaded_item"]) if self.__state["loaded_item"] else None
            self.__state["show_plan"] = [PlanObject(obj) for obj in self.__state["show_plan"]]

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, state):
        self.__state = state

        file = open(self.filepath, "w")
        
        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        state_to_json = copy.copy(state)
        state_to_json["loaded_item"] = state_to_json["loaded_item"].__dict__ if state_to_json["loaded_item"] else None
        state_to_json["show_plan"] = [repr.__dict__ for repr in state_to_json["show_plan"]]

        file.write(json.dumps(state_to_json, indent=2, sort_keys=True))

        file.close()

    def update(self, key, value):
        state = self.state
        state[key] = value
        self.state = state

    def log(self, msg):
        print(msg)
