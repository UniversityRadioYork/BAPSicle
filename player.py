"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    Audio Player, handles one audio item and plays it.

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        October, November 2020
"""

# This is the player. Reliability is critical here, so we're catching
# literally every exception possible and handling it.

# It is key that whenever the parent server tells us to do something
# that we respond with something, FAIL or OKAY. The server doesn't like to be kept waiting.

# Stop the Pygame Hello message.
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"

from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time
from typing import Any, Callable, Dict, List, Optional, Union
from pygame import mixer
from mutagen.mp3 import MP3
from syncer import sync
from threading import Timer

from helpers.myradio_api import MyRadioAPI
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from helpers.messages import encode_msg_dict, encode_msg_new, decode_msg
from baps_types.plan import PlanItem
from baps_types.marker import Marker
import package

# TODO ENUM
VALID_MESSAGE_SOURCES = ["CHANNEL"]
TRACKLISTING_DELAYED_S = 20


class Player:
    out_q: multiprocessing.Queue
    last_msg: dict
    last_time_update = None

    state: StateManager
    logger: LoggingManager
    api: MyRadioAPI

    running: bool = False

    stopped_manually: bool = False

    tracklist_start_timer: Optional[Timer] = None
    tracklist_end_timer: Optional[Timer] = None

    __default_state = {
        "initialised": False, # Did pygame start properly with the given output device?
        "loaded_item": None, # PlanItem of the current audio item to play.
        "channel": -1, # The channel this player is associated with. Multiple players can be on the same channel.
        "id": -1, # An ID for this player, this is unique per player instances on a channel.
        "playing": False,
        "paused": False,
        "loaded": False, # Is the file in memory, ready to play instantly?
        "cued": False, # Is the player at a cue point?
        "pos_elapsed": 0, # Time elapsed (secs) since starting current playback. This is pygame's position. WARN: It resets to 0 ever seek.
        "pos_offset": 0, # The difference (secs) between the pos_elapsed and the actual position in the file being played.
        "pos": 0, # The real amount of secs through the file we actually are. (pos = pos_elapsed + pos_offset)
        "remaining": 0, # Number of secs remaining of the file.
        "length": 0, # Length of file in secs.
        "repeat": False, # Should the player play again by itself if it reaches the end?
        "play_on_load": False, # Should the player play as soon as it is loaded?
        "output": None, # Name of the audio device to output on (str) or None for default system output.
        "tracklist_mode": "off",
        "tracklist_id": None,
    }

    __rate_limited_params = ["pos_elapsed", "pos_offset", "pos", "remaining"]

    @property
    def isInit(self):
        try:
            mixer.music.get_busy()
        except Exception:
            return False

        return True

    @property
    def isPlaying(self) -> bool:
        if self.isInit:
            return (not self.isPaused) and bool(mixer.music.get_busy())
        return False

    @property
    def isPaused(self) -> bool:
        return self.state.get()["paused"]

    @property
    def isLoaded(self):
        return self._isLoaded()

    # TODO: This probably runs FAR TOO OFTEN
    def _isLoaded(self, short_test: bool = False):
        if not self.state.get()["loaded_item"]:
            return False
        if self.isPlaying:
            return True

        # If we don't want to do any testing if it's really loaded, fine.
        if short_test:
            return True

        # Because Pygame/SDL is annoying
        # We're not playing now, so we can quickly test run
        # If that works, we're loaded.
        try:
            mixer.music.set_volume(0)
            mixer.music.play(0)
        except Exception:
            try:
                mixer.music.set_volume(1)
            except Exception:
                self.logger.log.exception(
                    "Failed to reset volume after attempting loaded test."
                )
                pass
            return False
        finally:
            mixer.music.stop()

        mixer.music.set_volume(1)
        return True

    @property
    def isCued(self):
        # Don't mess with playback, we only care about if it's supposed to be loaded.
        if not self._isLoaded(short_test=True):
            return False
        return (self.state.get()["pos"] == self.state.get()["loaded_item"].cue and not self.isPlaying)


    def _status(self, as_dict: Optional[bool] = False):
        state = copy.copy(self.state.state)

        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        state["loaded_item"] = (
            state["loaded_item"].__dict__ if state["loaded_item"] else None
        )
        if not as_dict:
            return json.dumps(state)
        return state

    @property
    def status(self):
        return self._status(as_dict = False)


    # Transport Controls

    def play(self, pos: float = 0):
        if not self.isLoaded:
            return
        self.logger.log.info("Playing from pos: " + str(pos))
        try:
            # Play from pos seconds into file.
            mixer.music.play(0, pos)
            # Since pos_elapsed will start from zero, store how far in we were when we started, as an offset.
            self.state.update("pos_offset", pos)
        except Exception:
            self.logger.log.exception("Failed to play at pos: " + str(pos))
            return False
        self.state.update("paused", False)
        self._potentially_tracklist()
        self.stopped_manually = False
        return True

    def pause(self):
        try:
            mixer.music.stop()
        except Exception:
            self.logger.log.exception("Failed to pause.")
            return False

        self.stopped_manually = True
        self.state.update("paused", True)
        return True

    def unpause(self):
        if not self.isPlaying:
            state = self.state.get()
            position: float = state["pos"]
            try:
                self.play(position)
            except Exception:
                self.logger.log.exception(
                    "Failed to unpause from pos: " + str(position)
                )
                return False

            self.state.update("paused", False)

            # Increment Played count
            loaded_item: Optional[PlanItem] = state["loaded_item"]
            if loaded_item:
                # TODO: Actually send this back to the channel
                loaded_item.play_count_increment()
                self.state.update("loaded_item", loaded_item)

            return True
        return False

    def stop(self, user_initiated: bool = False):
        try:
            mixer.music.stop()
        except Exception:
            self.logger.log.exception("Failed to stop playing.")
            return False
        self.state.update("paused", False)

        if user_initiated:
            self._potentially_end_tracklist()

        self.stopped_manually = True

        if not self.state.get()["loaded_item"]:
            self.logger.log.warning("Tried to stop without a loaded item.")
            return True

        # This lets users toggle (using the stop button) between cue point and 0.
        if user_initiated and not self.isCued:
            # if there's a cue point ant we're not at it, go there.
            self.seek(self.state.get()["loaded_item"].cue)
        else:
            # Otherwise, let's go to 0.
            self.seek(0)

        return True

    def seek(self, pos: float) -> bool:
        self.logger.log.info("Seeking to pos:" + str(pos))
        if self.isPlaying:
            try:
                self.play(pos)
            except Exception:
                self.logger.log.exception("Failed to seek to pos: " + str(pos))
                return False
            return True
        else:
            self.logger.log.debug("Not playing during seek, setting pos state for next play.")
            self.stopped_manually = True  # Don't trigger _ended() on seeking.
            if pos > 0:
                self.state.update("paused", True)
            self._updateState(pos=pos)
        return True

    # Set if the player should replay after reaching the end.
    def set_repeat(self, enabled: bool):
        self.state.update("repeat", bool(enabled))

    # Should the player play as soon as it's got the file ready?
    # Essentially a "PANIC! Play something!"
    def set_play_on_load(self, enabled: bool):
        self.state.update("play_on_load", bool(enabled))


    def load(self, new_item: Optional[Union[PlanItem,Dict[str,Any]]]):
        if not self.isPlaying:
            self.unload()

            if new_item is None:
                self.logger.log.info("No PlanItem given, unloaded")
                return False

            if isinstance(new_item, PlanItem):
                loaded_item = new_item # typically when reloading from inside the player.
            else:
                try:
                    loaded_item = PlanItem(new_item)
                except Exception:
                    self.logger.log.error("Failed to parse PlanItem to load.")
                    return False

            reload = False
            if loaded_item.filename == "" or loaded_item.filename is None:
                self.logger.log.info(
                    "Filename is not specified, loading from API.")
                reload = True
            elif not os.path.exists(loaded_item.filename):
                self.logger.log.warn(
                    "Filename given doesn't exist. Re-loading from API."
                )
                reload = True

            # TODO: Should we handle this here, or get channel, or some kind of handler to do this before hand? Normalisation etc?
            if reload:
                loaded_item.filename = str(sync(self.api.get_filename(item=loaded_item)))

            if loaded_item.filename is None or loaded_item.filename in ["None",""]:
                return False

            self.state.update("loaded_item", loaded_item)

            load_attempt = 0
            while load_attempt < 5:
                load_attempt += 1
                try:
                    self.logger.log.info("Loading file: " +
                                        str(loaded_item.filename))
                    mixer.music.load(loaded_item.filename)
                except Exception:
                    # We couldn't load that file.
                    self.logger.log.exception(
                        "Couldn't load file: " + str(loaded_item.filename)
                    )
                    time.sleep(1)
                    continue # Try loading again.

                if not self.isLoaded:
                    self.logger.log.error("Pygame loaded file without error, but never actually loaded.")
                    time.sleep(1)
                    continue # Try loading again.

                try:
                    if ".mp3" in loaded_item.filename:
                        song = MP3(loaded_item.filename)
                        self.state.update("length", song.info.length)
                    else:
                        # TODO: Pygame can't seek WAV files, so this is a bit unneccessary.
                        self.state.update(
                            "length", mixer.Sound(
                                loaded_item.filename).get_length() / 1000
                        )
                except Exception:
                    self.logger.log.exception(
                        "Failed to update the length of item.")
                    time.sleep(1)
                    continue # Try loading again.

                # Everything worked, we made it!
                if loaded_item.cue > 0:
                    self.seek(loaded_item.cue)
                else:
                    self.seek(0)

                if self.state.get()["play_on_load"]:
                    self.unpause()

                return True

            self.logger.log.error("Failed to load track after numerous retries.")
            return False

        return False

    def unload(self):
        if not self.isPlaying:
            try:
                mixer.music.unload()
                self.state.update("paused", False)
                self.state.update("loaded_item", None)
            except Exception:
                self.logger.log.exception("Failed to unload player.")
                return False

        self._potentially_end_tracklist()
        # If we unloaded successfully, reset the tracklist_id, ready for the next item.
        if not self.isLoaded:
            self.state.update("tracklist_id", None)

        return not self.isLoaded

    def quit(self):
        try:
            mixer.quit()
            self.state.update("paused", False)
            self.logger.log.info("Quit mixer.")
        except Exception:
            self.logger.log.exception("Failed to quit mixer.")

    def set_output(self, name: Optional[str] = None):
        wasPlaying = self.state.get()["playing"]
        oldPos = self.state.get()["pos"]

        name = None if (not name or name.lower() == "none") else name

        self.quit()
        self.state.update("output", name)
        try:
            if name:
                mixer.init(44100, -16, 2, 1024, devicename=name)
            else:
                mixer.init(44100, -16, 2, 1024)
        except Exception:
            self.logger.log.exception(
                "Failed to init mixer with device name: " + str(name)
            )
            return False

        loadedItem = self.state.get()["loaded_item"]
        if loadedItem:
            self.logger.log.info("Reloading after output change.")
            self.load(loadedItem)
        if wasPlaying:
            self.logger.log.info("Resuming playback after output change.")
            self.play(oldPos)

        return True

    # Timeslotitemid can be a ghost (un-submitted item), so may be "IXXX"
    def set_marker(self, timeslotitemid: str, marker_str: str):
        return

        set_loaded = False
        success = True
        try:
            marker = Marker(marker_str)
        except Exception as e:
            self.logger.log.error("Failed to create Marker instance with {} {}: {}".format(timeslotitemid, marker_str, e))
            return False

        if timeslotitemid == "-1":
            set_loaded = True
            if not self.isLoaded:
                return False
            timeslotitemid = self.state.get()["loaded_item"].timeslotitemid
        elif self.isLoaded and self.state.get()["loaded_item"].timeslotitemid == timeslotitemid:
            set_loaded = True


        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        for i in range(len(self.state.get()["show_plan"])):

            item = plan_copy[i]

            if str(item.timeslotitemid) == str(timeslotitemid):
                try:
                    new_item = item.set_marker(marker)
                    self.state.update("show_plan", new_item, index=i)

                except Exception as e:
                    self.logger.log.error(
                        "Failed to set marker on item {}: {} with marker \n{}".format(timeslotitemid, e, marker))
                    success = False

        if set_loaded:
            try:
                self.state.update("loaded_item", self.state.get()["loaded_item"].set_marker(marker))
            except Exception as e:
                self.logger.log.error(
                    "Failed to set marker on loaded_item {}: {} with marker \n{}".format(timeslotitemid, e, marker))
                success = False

        return success



    # Helper functions

    # This essentially allows the tracklist end API call to happen in a separate thread, to avoid hanging playout/loading.
    def _potentially_tracklist(self):
        mode = self.state.get()["tracklist_mode"]

        time: int = -1
        if mode == "on":
            time = 1  # Let's do it pretty quickly.
        elif mode == "delayed":
            # Let's do it in a bit, once we're sure it's been playing. (Useful if we've got no idea if it's live or cueing.)
            time = TRACKLISTING_DELAYED_S

        if time >= 0 and not self.tracklist_start_timer:
            self.logger.log.info("Setting timer for tracklisting in {} secs due to Mode: {}".format(time, mode))
            self.tracklist_start_timer = Timer(time, self._tracklist_start)
            self.tracklist_start_timer.start()
        elif self.tracklist_start_timer:
            self.logger.log.error("Failed to potentially tracklist, timer already busy.")

    # This essentially allows the tracklist end API call to happen in a separate thread, to avoid hanging playout/loading.
    def _potentially_end_tracklist(self):

        if self.tracklist_start_timer:
            self.logger.log.info("A tracklist start timer was running, cancelling.")
            self.tracklist_start_timer.cancel()
            self.tracklist_start_timer = None

            # Decrement Played count on track we didn't play much of.
            state = self.state.get()
            loaded_item: Optional[PlanItem] = state["loaded_item"]
            if loaded_item and loaded_item.type == "central":
                # TODO: Actually send this back to the channel
                loaded_item.play_count_decrement()
                self.state.update("loaded_item", loaded_item)

        # Make a copy of the tracklist_id, it will get reset as we load the next item.
        tracklist_id = self.state.get()["tracklist_id"]
        if not tracklist_id:
            self.logger.log.info("No tracklist to end.")
            return

        self.logger.log.info("Setting timer for ending tracklist_id {}".format(tracklist_id))
        if tracklist_id:
            self.logger.log.info("Attempting to end tracklist_id {}".format(tracklist_id))
            if self.tracklist_end_timer:
                self.logger.log.error("Failed to potentially end tracklist, timer already busy.")
                return
            # This threads it, so it won't hang track loading if it fails.
            self.tracklist_end_timer = Timer(1, self._tracklist_end, [tracklist_id])
            self.tracklist_end_timer.start()
        else:
            self.logger.log.warning("Failed to potentially end tracklist, no tracklist started.")

    def _tracklist_start(self):
        loaded_item = self.state.get()["loaded_item"]
        if not loaded_item:
            self.logger.log.error("Tried to call _tracklist_start() with no loaded item!")
            return

        tracklist_id = self.state.get()["tracklist_id"]
        if (not tracklist_id):
            self.logger.log.info("Tracklisting item: {}".format(loaded_item.name))
            tracklist_id = self.api.post_tracklist_start(loaded_item)
            if not tracklist_id:
                self.logger.log.warning("Failed to tracklist {}".format(loaded_item.name))
            else:
                self.logger.log.info("Tracklist id: {}".format(tracklist_id))
                self.state.update("tracklist_id", tracklist_id)
        else:
            self.logger.log.info("Not tracklisting item {}, already got tracklistid: {}".format(
                loaded_item.name, tracklist_id))

        self.tracklist_start_timer = None

    def _tracklist_end(self, tracklist_id):

        if tracklist_id:
            self.logger.log.info("Attempting to end tracklist_id {}".format(tracklist_id))
            self.api.post_tracklist_end(tracklist_id)
        else:
            self.logger.log.error("Tracklist_id to _tracklist_end() missing. Failed to end tracklist.")

        self.tracklist_end_timer = None

    def _ended(self):

        # TODO Send responses back to channel for play counts etc.

        self._potentially_end_tracklist()

        state = self.state.get()

        loaded_item = state["loaded_item"]

        if not loaded_item:
            return

        # Track has ended
        self.logger.log.info("Playback ended of {}, weight {}:".format(loaded_item.name, loaded_item.weight))

        # Repeat
        # TODO: Increment play count here?
        if state["repeat"]:
            self.play()
            return

        # No automations, just stop playing.
        self.stop()
        # Tell clients that we've stopped playing.
        custom_msg = encode_msg_new(src = "ALL", command = "STOPPED")
        self._send_to_channel(custom_msg)

    def _updateState(self, pos: Optional[float] = None):

        self.state.update("initialised", self.isInit)
        if self.isInit:
            if pos is not None:
                # Seeking sets the position like this when not playing.
                self.state.update("pos_elapsed", pos)  # Reset back to 0 if stopped.
                self.state.update("pos_offset", 0)
            elif self.isPlaying:
                # This is the bit that makes the time actually progress during playback.
                # Get one last update in, incase we're about to pause/stop it.
                self.state.update("pos_elapsed", max(0, mixer.music.get_pos() / 1000))

            # If the state is changing from playing to not playing, and the user didn't stop it, the item must have ended.
            if (
                self.state.get()["playing"]
                and not self.isPlaying
                and not self.stopped_manually
            ):
                self._ended()

            self.state.update("playing", self.isPlaying)
            self.state.update("loaded", self.isLoaded)
            self.state.update("cued", self.isCued)

            self.state.update(
                "pos",
                min(
                    self.state.get()["length"],
                    self.state.get()["pos_elapsed"] + self.state.get()["pos_offset"],
                ),
            )

            self.state.update(
                "remaining",
                max(0, (self.state.get()["length"] -
                    self.state.get()["pos"])),
            )

    def _ping_times(self):

        UPDATES_FREQ_SECS = 0.2
        if (
            self.last_time_update is None
            or self.last_time_update + UPDATES_FREQ_SECS < time.time()
        ):
            self.last_time_update = time.time()
            # POS is not requested, it's just spammed out, so need a custom response.
            extra = {
                "pos": self.state.get()["pos"]
            }

            custom_msg = encode_msg_new(src = "ALL", command = "POS", extra = extra)
            self._send_to_channel(custom_msg)


    def _ret_msg(self, okay: bool = True, reason:str = None):
        self._send_to_channel(
            encode_msg_dict(self.last_msg, okay)
        )


    def _send_to_channel(self, msg: str):
        if self.out_q:
            if "STATUS" not in msg and "POS" not in msg:
                # Don't fill logs with pos/status pushes, it's a mess.
                self.logger.log.debug(("Sending: {}".format(msg)))
            self.out_q.put(msg)
        else:
            self.logger.log.exception("Message return Queue is missing!!!! Can't send message.")

    def _send_status(self):
        self._send_to_channel(
            encode_msg_new(
                src="ALL",
                command="STATUS",
                status=self.isInit,
                extra=self._status(as_dict=True) # Need dict so it's not double json.dumps'd.
            )
        )

    def __init__(
        self, channel: int, id: int, in_q: multiprocessing.Queue, out_q: multiprocessing.Queue, server_state: StateManager
    ):

        player_name = "Channel{}-Player{}".format(channel,id)

        setproctitle.setproctitle(player_name)
        multiprocessing.current_process().name = player_name

        self.running = True
        self.out_q = out_q


        self.logger = LoggingManager(player_name, debug=False)#package.build_beta)

        self.api = MyRadioAPI(self.logger, server_state)

        self.state = StateManager(
            player_name,
            self.logger,
            self.__default_state,
            self.__rate_limited_params,
        )

        self.state.update("channel", channel)
        self.state.update("id", id)
        self.state.update("tracklist_mode", server_state.get()["tracklist_mode"])

        self.state.add_callback(self._send_status)

        loaded_state = copy.copy(self.state.state)

        if loaded_state["output"]:
            self.logger.log.info("Setting output to: " +
                                 str(loaded_state["output"]))
            self.set_output(loaded_state["output"])
        else:
            self.logger.log.info("Using default output device.")
            self.set_output()

        loaded_item = loaded_state["loaded_item"]
        if loaded_item:
            # No need to load on init, the output switch does this, as it would for regular output switching.
            #self.load(loaded_item)

            # Load may jump to the cue point, as it would do on a regular load.
            # If we were at a different state before, we have to override it now.
            if loaded_state["pos"] != 0:
                self.logger.log.info(
                    "Seeking to pos: " + str(loaded_state["pos"])
                )
                self.seek(loaded_state["pos"])

            if loaded_state["playing"] is True:
                self.logger.log.info("Resuming playback on init.")
                self.unpause()  # Use un-pause as we don't want to jump to a new position.
        else:
            self.logger.log.info("No file was previously loaded to resume.")

        try:
            while self.running:
                time.sleep(0.03)
                self._updateState()
                self._ping_times()
                try:
                    message = in_q.get_nowait()
                    # TODO: Validate this
                    self.last_msg = decode_msg(message)

                    source = self.last_msg["src"]
                    if source not in VALID_MESSAGE_SOURCES:
                        self.last_msg = {}
                        self.logger.log.warn(
                            "Message from unknown sender source: {}".format(
                                source)
                        )
                        continue

                    self.logger.log.debug(
                        "Recieved message from source {}: {}".format(
                            source, self.last_msg
                        )
                    )
                except Empty:
                    # The incomming message queue was empty,
                    # skip message processing
                    pass
                else:

                    # We got a message.
                    extra = self.last_msg["extra"] if self.last_msg["extra"] else {}

                    # Output re-inits the mixer, so we can do this any time.
                    if self.last_msg["command"] == "OUTPUT":
                        self._ret_msg(self.set_output(self.last_msg["extra"]["name"]))

                    elif self.isInit:





                        commands: Dict[
                            str, Callable[..., Any]
                        ] = {  # TODO Check Types
                            "STATUS": lambda: self._send_status(),

                            # Audio Playout
                            # Unpause, so we don't jump to 0, we play from the current pos.
                            "PLAY": lambda: self.unpause(),
                            "PAUSE": lambda: self.pause(),
                            "PLAYPAUSE": lambda: self.unpause() if not self.isPlaying else self.pause(), # For the hardware controller.
                            "UNPAUSE": lambda: self.unpause(),
                            "STOP": lambda: self.stop(user_initiated=True),
                            "SEEK": lambda:
                                self.seek(float(extra["pos"]))
                            ,
                            "REPEAT": lambda:
                                self.set_repeat(bool(extra["enabled"]))
                            ,
                            "PLAYONLOAD": lambda:
                                self.set_play_on_load(
                                    (bool(extra["enabled"]))
                                )
                            ,
                            "LOAD": lambda:
                                self.load(extra)
                            ,
                            "LOADED?": lambda: self.isLoaded,
                            "UNLOAD": lambda: self.unload(),
                            "SETMARKER": lambda: self.set_marker(extra["timeslotitemid"],extra["marker"]),
                        }

                        command: str = self.last_msg["command"]

                        if command in commands.keys():
                            self._ret_msg(okay=commands[command]()) # Each func in the dict returns a success bool.

                        elif self.last_msg == "QUIT":
                            self._ret_msg(True)
                            self.running = False
                            continue

                        else:
                            self._ret_msg(okay=False, reason="Unknown Command")
                    else:

                        if self.last_msg == "STATUS":
                            self._send_status()
                            self._ret_msg(okay=True)
                        else:
                            self._ret_msg(okay=False, reason="Player is not initialised.")

        # Catch the player being killed externally.
        except KeyboardInterrupt:
            self.logger.log.info("Received KeyboardInterupt")
        except SystemExit:
            self.logger.log.info("Received SystemExit")
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected Exception: {}".format(e))

        self.logger.log.info("Quiting " + player_name)
        self.quit()
        custom_msg = encode_msg_new(src = "ALL", command = "QUIT")
        self._send_to_channel(custom_msg)
        del self.logger
        os._exit(0)


if __name__ == "__main__":
    raise Exception(
        "This BAPSicle Player is a subcomponenet, it will not run individually."
    )
