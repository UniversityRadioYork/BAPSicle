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

from types.marker import Marker
from typing import Any, Dict, Optional
import os


class PlanItem:
    _timeslotitemid: int = 0
    _weight: int = 0
    _filename: Optional[str]
    _title: str
    _artist: Optional[str]
    _trackid: Optional[int]
    _managedid: Optional[int]

    @property
    def weight(self) -> int:
        return self._weight

    @weight.setter
    def weight(self, value: int):
        self._weight = value

    @property
    def timeslotitemid(self) -> int:
        return self._timeslotitemid

    @property
    def filename(self) -> Optional[str]:
        return self._filename

    @filename.setter
    def filename(self, value: Optional[str]):
        self._filename = value

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
        }

    def __init__(self, new_item: Dict[str, Any]):
        self._timeslotitemid = new_item["timeslotitemid"]
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

        # Edit this to handle markers when MyRadio supports them
        self._

        # Fix any OS specific / or \'s
        if self.filename:
            if os.path.sep == "/":
                self._filename = self.filename.replace("\\", "/")
            else:
                self._filename = self.filename.replace("/", "\\")

    def set_marker(self, marker: Marker):
        if not isinstance(marker, Marker):
            raise ValueError("Marker provided is not of type Marker.")

        # Return updated item for easy chaining.
        return self
