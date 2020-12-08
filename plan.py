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

from typing import Dict
import os

class PlanItem:
    _timeslotItemId: int = 0
    _filename: str = ""
    _title: str = ""
    _artist: str = ""
    _trackId: int = None
    _managedId: int = None

    @property
    def timeslotItemId(self) -> int:
        return self._timeslotItemId

    @property
    def filename(self) -> str:
        return self._filename

    @filename.setter
    def filename(self, value: str):
        self._filename = value

    @property
    def name(self) -> str:
        return "{0} - {1}".format(self._title, self._artist) if self._artist else self._title

    @property
    def trackId(self) -> int:
        return self._trackId

    @property
    def managedId(self) -> int:
        return self._managedId

    @property
    def __dict__(self) -> Dict[str, any]:
        return {
            "timeslotItemId": self.timeslotItemId,
            "trackId": self._trackId,
            "managedId": self._managedId,
            "title": self._title,
            "artist": self._artist,
            "name": self.name,
            "filename": self.filename
        }

    def __init__(self, new_item: Dict[str, any]):
        self._timeslotItemId = new_item["timeslotItemId"]
        self._trackId = new_item["trackId"] if "trackId" in new_item else None
        self._managedId = new_item["managedId"] if "managedId" in new_item else None
        self._filename = new_item["filename"] # This could be a temp dir for API-downloaded items, or a mapped drive.
        self._title = new_item["title"]
        self._artist = new_item["artist"]

        # Fix any OS specific / or \'s
        if self.filename:
            if os.path.sep == "/":
                self._filename = self.filename.replace("\\", '/')
            else:
                self._filename = self.filename.replace("/", '\\')
