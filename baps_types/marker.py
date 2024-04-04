import json
from typing import Dict, Optional, Union

POSITIONS = ["start", "mid", "end"]
PARAMS = ["name", "time", "position", "section"]


class Marker:
    marker: Dict

    def __init__(self, new_marker: Union[str, dict]):
        marker: dict
        try:
            if isinstance(new_marker, str):
                marker = json.loads(new_marker)
            else:
                marker = new_marker
        except Exception as e:
            raise ValueError("Failed to decode JSON for marker: {}".format(e))

        for key in marker.keys():
            if key not in PARAMS:
                raise ValueError("Key {} is not a valid marker parameter.".format(key))

        if not isinstance(marker["name"], str):
            raise ValueError("Name is not str.")

        if not (isinstance(marker["time"], int) or isinstance(marker["time"], float)):
            raise ValueError("Time is not a float or int")

        if marker["position"] not in POSITIONS:
            raise ValueError("Position is not in allowed values.")

        if not (marker["section"] is None or isinstance(marker["section"], str)):
            raise ValueError("Section name is not str or None.")

        marker["time"] = float(marker["time"])
        # If everything checks out, let's save it.
        self.marker = marker

    @property
    def __str__(self) -> str:
        return json.dumps(self.marker)

    @property
    def __dict__(self) -> dict:
        return self.marker

    @property
    def name(self) -> str:
        return self.marker["name"]

    @property
    def time(self) -> float:
        return float(self.marker["time"])

    @property
    def position(self) -> str:
        return self.marker["position"]

    @property
    def section(self) -> Optional[str]:
        return self.marker["section"]

    def same_type(self, o: object) -> bool:
        if not isinstance(o, Marker):
            return False
        return o.position == self.position and o.section == self.section
