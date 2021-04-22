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
import aiohttp
import json
from logging import INFO, ERROR, WARNING
import os
import requests

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

    async def async_call(self, url, method="GET", data=None, timeout=10):

        async with aiohttp.ClientSession(read_timeout=timeout) as session:
            func = session.get(url)
            status_code = -1
            if method == "GET":
                #func = session.get(url)
                status_code = 200
            elif method == "POST":
                func = session.post(url, data=data)
                status_code = 201
            elif method == "PUT":
                func = session.put(url)
                status_code = 201

            async with func as response:
                if response.status != status_code:
                    self._logException(
                        "Failed to get API request. Status code: " + str(response.status)
                    )
                    self._logException(str(response.text()))
                return await response.read()

    def call(self, url, method="GET", data=None, timeout=10, json_payload=True):
        r = None
        status_code = -1
        if method == "GET":
            r = requests.get(url, timeout=timeout)
            status_code = 200
        elif method == "POST":
            r = requests.post(url, data, timeout=timeout)
            status_code = 201
        elif method == "PUT":
            r = requests.put(url, data, timeout=timeout)
            status_code = 200

        if r.status_code != status_code:
            self._logException(
                "Failed to get API request. Status code: " + str(r.status_code)
            )
            self._logException(str(r.text))
        return json.loads(r.text) if json_payload else r.text

    async def async_api_call(self, url, api_version="v2", method="GET", data=None, timeout=10):
        if api_version == "v2":
            url = "{}/v2{}".format(self.config.get()["myradio_api_url"], url)
        elif api_version == "non":
            url = "{}{}".format(self.config.get()["myradio_base_url"], url)
        else:
            self._logException("Invalid API version. Request not sent.")
            return None

        if "?" in url:
            url += "&api_key={}".format(self.config.get()["myradio_api_key"])
        else:
            url += "?api_key={}".format(self.config.get()["myradio_api_key"])

        self._log("Requesting API V2 URL with method {}: {}".format(method, url))

        request = None
        if method == "GET":
            request = self.async_call(url, method="GET", timeout=timeout)
        elif method == "POST":
            self._log("POST data: {}".format(data))
            request = self.async_call(url, data=data, method="POST", timeout=timeout)
        elif method == "PUT":
            request = self.async_call(url, method="PUT", timeout=timeout)
        else:
            self._logException("Invalid API method. Request not sent.")
            return None
        self._log("Finished request.")

        return request

    def api_call(self, url, api_version="v2", method="GET", data=None, timeout=10):

        if api_version == "v2":
            url = "{}/v2{}".format(self.config.get()["myradio_api_url"], url)
        elif api_version == "non":
            url = "{}{}".format(self.config.get()["myradio_base_url"], url)
        else:
            self._logException("Invalid API version. Request not sent.")
            return None

        if "?" in url:
            url += "&api_key={}".format(self.config.get()["myradio_api_key"])
        else:
            url += "?api_key={}".format(self.config.get()["myradio_api_key"])

        self._log("Requesting API V2 URL with method {}: {}".format(method, url))

        request = None
        if method == "GET":
            request = self.call(url, method="GET", timeout=timeout)
        elif method == "POST":
            self._log("POST data: {}".format(data))
            request = self.call(url, data=data, method="POST", timeout=timeout)
        elif method == "PUT":
            request = self.call(url, method="PUT", timeout=timeout)
        else:
            self._logException("Invalid API method. Request not sent.")
            return None
        self._log("Finished request.")

        return request

    # Show plans

    async def get_showplans(self):
        url = "/timeslot/currentandnextobjects?n=10"
        request = await self.async_api_call(url)

        if not request:
            self._logException("Failed to get list of show plans.")
            return None

        payload = json.loads(await request)["payload"]

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

    async def get_showplan(self, timeslotid: int):

        url = "/timeslot/{}/showplan".format(timeslotid)
        request = await self.async_api_call(url)

        if not request:
            self._logException("Failed to get show plan.")
            return None

        return json.loads(await request)["payload"]

    # Audio Library

    async def get_filename(self, item: PlanItem):
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
        request = await self.async_api_call(url, api_version="non")

        if not request:
            return None

        try:
            with open(filename, "wb") as file:
                file.write(await request)
        except Exception as e:
            self._logException("Failed to write music file: {}".format(e))
            return None

        return filename

    # Gets the list of managed music playlists.
    async def get_playlist_music(self):
        url = "/playlist/allitonesplaylists"
        request = await self.async_api_call(url)

        if not request:
            self._logException("Failed to retrieve music playlists.")
            return None

        return json.loads(await request)["payload"]

    # Gets the list of managed aux playlists (sfx, beds etc.)
    async def get_playlist_aux(self):
        url = "/nipswebPlaylist/allmanagedplaylists"
        request = await self.async_api_call(url)

        if not request:
            self._logException("Failed to retrieve music playlists.")
            return None

        return json.loads(await request)["payload"]

    # Loads the playlist items for a certain managed aux playlist
    async def get_playlist_aux_items(self, library_id: str):
        # Sometimes they have "aux-<ID>", we only need the index.
        if library_id.index("-") > -1:
            library_id = library_id[library_id.index("-") + 1:]

        url = "/nipswebPlaylist/{}/items".format(library_id)
        request = await self.async_api_call(url)

        if not request:
            self._logException(
                "Failed to retrieve items for aux playlist {}.".format(library_id)
            )
            return None

        return json.loads(await request)["payload"]

        # Loads the playlist items for a certain managed playlist

    async def get_playlist_music_items(self, library_id: str):
        url = "/playlist/{}/tracks".format(library_id)
        request = await self.async_api_call(url)

        if not request:
            self._logException(
                "Failed to retrieve items for music playlist {}.".format(library_id)
            )
            return None

        return json.loads(await request)["payload"]

    async def get_track_search(
        self, title: Optional[str], artist: Optional[str], limit: int = 100
    ):
        url = "/track/search?title={}&artist={}&digitised=1&limit={}".format(
            title if title else "", artist if artist else "", limit
        )
        request = await self.async_api_call(url)

        if not request:
            self._logException("Failed to search for track.")
            return None

        return json.loads(await request)["payload"]

    def post_tracklist_start(self, item: PlanItem):
        if item.type != "central":
            self._log("Not tracklisting, {} is not a track.".format(item.name))
            return False

        self._log("Tracklisting item: {}".format(item.name))

        source: str = self.config.get()["myradio_api_tracklist_source"]
        data = {
            "trackid": item.trackid,
            "sourceid": int(source) if source.isnumeric() else source
        }
        # Starttime and timeslotid are default in the API to current time/show.
        tracklist_id = None
        try:
            tracklist_id = self.api_call("/tracklistItem/", method="POST", data=data)["payload"]["audiologid"]
        except Exception as e:
            self._logException("Failed to get tracklistid. {}".format(e))

        if not tracklist_id or not isinstance(tracklist_id, int):
            self._log("Failed to tracklist! API rejected tracklist.", ERROR)
            return
        return tracklist_id

    def post_tracklist_end(self, tracklistitemid: int):
        if not tracklistitemid:
            self._log("Tracklistitemid is None, can't end tracklist.", WARNING)
            return False
        if not isinstance(tracklistitemid, int):
            self._logException("Tracklistitemid '{}' is not an integer!".format(tracklistitemid))
            return False

        self._log("Ending tracklistitemid {}".format(tracklistitemid))

        result = self.api_call("/tracklistItem/{}/endtime".format(tracklistitemid), method="PUT")
        print(result)

    def _log(self, text: str, level: int = INFO):
        self.logger.log.log(level, "MyRadio API: " + text)

    def _logException(self, text: str):
        self.logger.log.exception("MyRadio API: " + text)
