"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    Show Plan Items

    Authors:
        Michael Grace

    Date:
        November 2020
"""


import json
from typing import Any, Dict, List, Optional, Union
import os

from baps_types.marker import Marker

from json import JSONEncoder
class PlanItemEncoder(JSONEncoder):
        def default(self, o):
            return o.__dict__
class PlanItem:
    _timeslotitemid: str = "0"
    _weight: int = 0
    _filename: Optional[str]
    _title: str
    _artist: Optional[str]
    _trackid: Optional[int]
    _managedid: Optional[int]
    _markers: List[Marker] = []
    _play_count: int
    _clean: bool

    @property
    def weight(self) -> int:
        return self._weight

    @weight.setter
    def weight(self, value: int):
        self._weight = value

    @property
    def timeslotitemid(self) -> str:
        return self._timeslotitemid

    @timeslotitemid.setter
    def timeslotitemid(self, value):
        self._timeslotitemid = str(value)

    @property
    def filename(self) -> Optional[str]:
        return self._filename

    @filename.setter
    def filename(self, value: Optional[str]):
        self._filename = value

    @property
    def play_count(self) -> int:
        return self._play_count

    def play_count_increment(self):
        self._play_count += 1

    def play_count_decrement(self):
        self._play_count = max(0,self._play_count - 1)

    def play_count_reset(self):
        self._play_count = 0

    @property
    def name(self) -> str:
        return (
            "{0} - {1}".format(self._title, self._artist)
            if self._artist
            else self._title
        )

    @property
    def trackid(self) -> Optional[int]:
        return self._trackid

    @property
    def managedid(self) -> Optional[int]:
        return self._managedid

    @property
    def title(self) -> Optional[str]:
        return self._title

    @property
    def artist(self) -> Optional[str]:
        return self._artist

    @property
    def length(self) -> Optional[str]:
        return self._length

    @property
    def type(self) -> Optional[str]:
        return "aux" if self.managedid else "central"

    @property
    def clean(self) -> bool:
        return self._clean

    @property
    def intro(self) -> float:
        markers = list(filter(lambda m: m.position == "start" and m.section is None, self._markers))
        # TODO: Handle multiple (shouldn't happen?)
        if len(markers) > 0:
            return markers[0].time
        return 0

    @property
    def cue(self) -> float:
        markers = list(filter(lambda m: m.position == "mid" and m.section is None, self._markers))
        # TODO: Handle multiple (shouldn't happen?)
        if len(markers) > 0:
            return markers[0].time
        return 0

    @property
    def outro(self) -> float:
        markers = list(filter(lambda m: m.position == "end" and m.section is None, self._markers))
        # TODO: Handle multiple (shouldn't happen?)
        if len(markers) > 0:
            return markers[0].time
        return 0

    @property
    def markers(self) -> List[dict]:
        return [repr.__dict__ for repr in self._markers]

    @property
    def __dict__(self):
        return {
            "weight": self.weight,
            "timeslotitemid": self.timeslotitemid,
            "trackid": self._trackid,
            "type": self.type,
            "managedid": self._managedid,
            "title": self._title,
            "artist": self._artist,
            "name": self.name,
            "filename": self.filename,
            "length": self.length,
            "intro": self.intro,
            "cue": self.cue,
            "outro": self.outro,
            "markers": self.markers,
            "played": self.play_count > 0,
            "play_count": self.play_count,
            "clean": self.clean
        }

    def __init__(self, new_item: Dict[str, Any]):
        self._timeslotitemid = str(new_item["timeslotitemid"])
        self._managedid = new_item["managedid"] if "managedid" in new_item else None
        self._trackid = (
            int(new_item["trackid"])
            if "trackid" in new_item and not self._managedid
            else None
        )
        self._filename = (
            new_item["filename"] if "filename" in new_item else None
        )  # This could be a temp dir for API-downloaded items, or a mapped drive.
        self._weight = int(new_item["weight"])
        self._title = new_item["title"]
        self._artist = new_item["artist"] if "artist" in new_item else None
        self._length = new_item["length"]
        self._markers = (
            [Marker(marker) for marker in new_item["markers"]] if "markers" in new_item else []
        )
        self._play_count = new_item["play_count"] if "play_count" in new_item else 0
        self._clean = new_item["clean"] if "clean" in new_item else True

        # TODO: Edit this to handle markers when MyRadio supports them
        if "intro" in new_item and (isinstance(new_item["intro"], int) or isinstance(new_item["intro"], float)) and new_item["intro"] > 0:
            marker = {
                "name": "Intro",
                "time": new_item["intro"],
                "position": "start",
                "section": None
            }
            self.set_marker(Marker(json.dumps(marker)))
        if "cue" in new_item and (isinstance(new_item["cue"], int) or isinstance(new_item["cue"], float)) and new_item["cue"] > 0:
            marker = {
                "name": "Cue",
                "time": new_item["cue"],
                "position": "mid",
                "section": None
            }
            self.set_marker(Marker(json.dumps(marker)))
        # TODO: Convert / handle outro being from end of item.
        if "outro" in new_item and (isinstance(new_item["outro"], int) or isinstance(new_item["outro"], float)) and new_item["outro"] > 0:
            marker = {
                "name": "Outro",
                "time": new_item["outro"],
                "position": "end",
                "section": None
            }
            self.set_marker(Marker(json.dumps(marker)))


        # Fix any OS specific / or \'s
        if self.filename:
            if os.path.sep == "/":
                self._filename = self.filename.replace("\\", "/")
            else:
                self._filename = self.filename.replace("/", "\\")

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, PlanItem):
            return False

        return o.__dict__ == self.__dict__

    def set_marker(self, new_marker: Marker):
        if not isinstance(new_marker, Marker):
            raise ValueError("Marker provided is not of type Marker.")

        replaced = False
        new_markers = []
        for marker in self._markers:
            if marker.same_type(new_marker):
                # Only add new marker if the marker is > 0 (to delete markers otherwise)
                if new_marker.time != 0:
                    new_markers.append(new_marker)
                # Replace marker
                replaced = True
            else:
                new_markers.append(marker)

        if not replaced:
            new_markers.append(new_marker)

        self._markers = new_markers

        # Return updated item for easy chaining.
        return self
