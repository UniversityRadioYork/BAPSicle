import json
import os


class StateManager:
    filepath = None
    __state = {}

    def __init__(self, name, default_state=None):
        self.filepath = "state/" + name + ".json"
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

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, state):
        self.__state = state

        file = open(self.filepath, "w")

        file.write(json.dumps(state, indent=2, sort_keys=True))

        file.close()

    def update(self, key, value):
        state = self.state
        state[key] = value
        self.state = state

    def log(self, msg):
        print(msg)
