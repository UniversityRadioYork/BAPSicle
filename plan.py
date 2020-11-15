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


class PlanObject:
    _channel_weight: int = 0
    _filename: str = ""
    _title: str = ""
    _artist: str = ""

    @property
    def channel_weight(self) -> int:
        return self._channel_weight

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def name(self) -> str:
        return "{0} - {1}".format(self._title, self._artist) if self._artist else self._title

    @property
    def __dict__(self) -> Dict[str, any]:
        return {
            "channel_weight": self.channel_weight,
            "title": self._title,
            "artist": self._artist,
            "name": self.name,
            "filename": self.filename
        }

    def __init__(self, new_item: Dict[str, any]):
        self._channel_weight = new_item["channel_weight"]
        self._filename = new_item["filename"]
        self._title = new_item["title"]
        self._artist = new_item["artist"]

        # Fix any OS specific / or \'s
        if os.path.sep == "/":
            self._filename = self.filename.replace("\\", '/')
        else:
            self._filename = self.filename.replace("/", '\\')
