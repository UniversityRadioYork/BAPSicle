import json
from typing import Dict, Optional, Union

POSITIONS = ["start", "mid", "end"]
PARAMS = ["name", "time", "position", "section"]


class Marker:
    marker: Dict

    def __init__(self, marker_str: str):
        try:
            marker = json.loads(marker_str)
        except Exception as e:
            raise ValueError("Failed to decode JSON for marker: {}".format(e))

        for key in marker.keys():
            if key not in PARAMS:
                raise ValueError("Key {} is not a valid marker parameter.".format(key))

        if not isinstance(marker["name"], str):
            raise ValueError("Name is not str.")
        self.name = marker["name"]

        if not isinstance(marker["time"], Union[int, float]):
            raise ValueError("Time is not a float or int")

        if marker["position"] not in POSITIONS:
            raise ValueError("Position is not in allowed values.")

        if not isinstance(marker["section"], Optional[str]):
            raise ValueError("Section name is not str or None.")

        # If everything checks out, let's save it.
        self.marker = marker

    def __str__(self):
        return json.dumps(self.marker)

    def __dict__(self):
        return self.marker
