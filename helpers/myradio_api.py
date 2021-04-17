"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    MyRadio API Handler

    In an ideal world, this module gives out and is fed PlanItems.
    This means it can be swapped for a different backend in the (unlikely) event
    someone else wants to integrate BAPsicle with something else.

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        November 2020
"""
from typing import Optional
import requests
import json
from logging import INFO
import os

from baps_types.plan import PlanItem
from helpers.os_environment import resolve_external_file_path
from helpers.logging_manager import LoggingManager
from helpers.state_manager import StateManager


class MyRadioAPI:
    logger: LoggingManager
    config: StateManager

    def __init__(self, logger: LoggingManager, config: StateManager):
        self.logger = logger
        self.config = config

    def get_non_api_call(self, url):

        url = "{}{}".format(self.config.state["myradio_base_url"], url)

        if "?" in url:
            url += "&api_key={}".format(self.config.state["myradio_api_key"])
        else:
            url += "?api_key={}".format(self.config.state["myradio_api_key"])

        self._log("Requesting non-API URL: " + url)
        request = requests.get(url, timeout=10)
        self._log("Finished request.")

        if request.status_code != 200:
            self._logException(
                "Failed to get API request. Status code: " + str(request.status_code)
            )
            self._logException(str(request.content))
            return None

        return request

    def get_apiv2_call(self, url):

        url = "{}/v2{}".format(self.config.state["myradio_api_url"], url)

        if "?" in url:
            url += "&api_key={}".format(self.config.state["myradio_api_key"])
        else:
            url += "?api_key={}".format(self.config.state["myradio_api_key"])

        self._log("Requesting API V2 URL: " + url)
        request = requests.get(url, timeout=10)
        self._log("Finished request.")

        if request.status_code != 200:
            self._logException(
                "Failed to get API request. Status code: " + str(request.status_code)
            )
            self._logException(str(request.content))
            return None

        return request

    # Show plans

    def get_showplans(self):
        url = "/timeslot/currentandnextobjects?n=10"
        request = self.get_apiv2_call(url)

        if not request:
            self._logException("Failed to get list of show plans.")
            return None

        payload = json.loads(request.content)["payload"]

        if not payload["current"]:
            self._logException("API did not return a current show.")

        if not payload["next"]:
            self._logException("API did not return a list of next shows.")

        shows = []
        shows.append(payload["current"])
        shows.extend(payload["next"])

        timeslots = []
        # Remove jukebox etc
        for show in shows:
            if not "timeslot_id" in show:
                shows.remove(show)

        # TODO filter out jukebox
        return shows

    def get_showplan(self, timeslotid: int):

        url = "/timeslot/{}/showplan".format(timeslotid)
        request = self.get_apiv2_call(url)

        if not request:
            self._logException("Failed to get show plan.")
            return None

        return json.loads(request.content)["payload"]

    # Audio Library

    def get_filename(self, item: PlanItem):
        format = "mp3"  # TODO: Maybe we want this customisable?
        if item.trackid:
            itemType = "track"
            id = item.trackid
            url = "/NIPSWeb/secure_play?trackid={}&{}".format(id, format)

        elif item.managedid:
            itemType = "managed"
            id = item.managedid
            url = "/NIPSWeb/managed_play?managedid={}".format(id)

        else:
            return None

        # Now check if the file already exists
        path: str = resolve_external_file_path("/music-tmp/")

        if not os.path.isdir(path):
            self._log("Music-tmp folder is missing, attempting to create.")
            try:
                os.mkdir(path)
            except Exception as e:
                self._logException("Failed to create music-tmp folder: {}".format(e))
                return None

        filename: str = resolve_external_file_path(
            "/music-tmp/{}-{}.{}".format(itemType, id, format)
        )

        if os.path.isfile(filename):
            return filename

        # File doesn't exist, download it.
        request = self.get_non_api_call(url)

        if not request:
            return None

        try:
            with open(filename, "wb") as file:
                file.write(request.content)
        except Exception as e:
            self._logException("Failed to write music file: {}".format(e))
            return None

        return filename

    # Gets the list of managed music playlists.
    def get_playlist_music(self):
        url = "/playlist/allitonesplaylists"
        request = self.get_apiv2_call(url)

        if not request:
            self._logException("Failed to retrieve music playlists.")
            return None

        return json.loads(request.content)["payload"]

    # Gets the list of managed aux playlists (sfx, beds etc.)
    def get_playlist_aux(self):
        url = "/nipswebPlaylist/allmanagedplaylists"
        request = self.get_apiv2_call(url)

        if not request:
            self._logException("Failed to retrieve music playlists.")
            return None

        return json.loads(request.content)["payload"]

    # Loads the playlist items for a certain managed aux playlist
    def get_playlist_aux_items(self, library_id: str):
        # Sometimes they have "aux-<ID>", we only need the index.
        if library_id.index("-") > -1:
            library_id = library_id[library_id.index("-") + 1:]

        url = "/nipswebPlaylist/{}/items".format(library_id)
        request = self.get_apiv2_call(url)

        if not request:
            self._logException(
                "Failed to retrieve items for aux playlist {}.".format(library_id)
            )
            return None

        return json.loads(request.content)["payload"]

        # Loads the playlist items for a certain managed playlist

    def get_playlist_music_items(self, library_id: str):
        url = "/playlist/{}/tracks".format(library_id)
        request = self.get_apiv2_call(url)

        if not request:
            self._logException(
                "Failed to retrieve items for music playlist {}.".format(library_id)
            )
            return None

        return json.loads(request.content)["payload"]

    def get_track_search(
        self, title: Optional[str], artist: Optional[str], limit: int = 100
    ):
        url = "/track/search?title={}&artist={}&digitised=1&limit={}".format(
            title if title else "", artist if artist else "", limit
        )
        request = self.get_apiv2_call(url)

        if not request:
            self._logException("Failed to search for track.")
            return None

        return json.loads(request.content)["payload"]

    def _log(self, text: str, level: int = INFO):
        self.logger.log.log(level, "MyRadio API: " + text)

    def _logException(self, text: str):
        self.logger.log.exception("MyRadio API: " + text)
