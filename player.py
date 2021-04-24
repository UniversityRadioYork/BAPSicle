"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    Audio Player

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
from typing import Any, Callable, Dict, List, Optional
from pygame import mixer
from mutagen.mp3 import MP3
from syncer import sync
from threading import Timer

from helpers.myradio_api import MyRadioAPI
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from baps_types.plan import PlanItem
from baps_types.marker import Marker

# TODO ENUM
VALID_MESSAGE_SOURCES = ["WEBSOCKET", "UI", "CONTROLLER", "TEST", "ALL"]
TRACKLISTING_DELAYED_S = 20


class Player:
    out_q: multiprocessing.Queue
    last_msg: str
    last_msg_source: str
    last_time_update = None

    state: StateManager
    logger: LoggingManager
    api: MyRadioAPI

    running: bool = False

    stopped_manually: bool = False

    tracklist_start_timer: Optional[Timer] = None
    tracklist_end_timer: Optional[Timer] = None

    __default_state = {
        "initialised": False,
        "loaded_item": None,
        "channel": -1,
        "playing": False,
        "paused": False,
        "loaded": False,
        "pos": 0,
        "pos_offset": 0,
        "pos_true": 0,
        "remaining": 0,
        "length": 0,
        "auto_advance": True,
        "repeat": "none",  # none, one or all
        "play_on_load": False,
        "output": None,
        "show_plan": [],
        "tracklist_mode": "off",
        "tracklist_id": None,
    }

    __rate_limited_params = ["pos", "pos_offset", "pos_true", "remaining"]

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
        return (self.state.get()["pos_true"] == self.state.get()["loaded_item"].cue and not self.isPlaying)

    @property
    def status(self):
        state = copy.copy(self.state.state)

        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        state["loaded_item"] = (
            state["loaded_item"].__dict__ if state["loaded_item"] else None
        )
        state["show_plan"] = [repr.__dict__ for repr in state["show_plan"]]

        res = json.dumps(state)
        return res

    # Audio Playout Related Methods

    def play(self, pos: float = 0):
        if not self.isLoaded:
            return

        try:
            mixer.music.play(0, pos)
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
            position: float = self.state.get()["pos_true"]
            try:
                self.play(position)
            except Exception:
                self.logger.log.exception(
                    "Failed to unpause from pos: " + str(position)
                )
                return False

            self.state.update("paused", False)
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
        if self.isPlaying:
            try:
                self.play(pos)
            except Exception:
                self.logger.log.exception("Failed to seek to pos: " + str(pos))
                return False
            return True
        else:
            self.stopped_manually = True  # Don't trigger _ended() on seeking.
            if pos > 0:
                self.state.update("paused", True)
            self._updateState(pos=pos)
        return True

    def set_auto_advance(self, message: bool) -> bool:
        self.state.update("auto_advance", message)
        return True

    def set_repeat(self, message: str) -> bool:
        if message in ["all", "one", "none"]:
            self.state.update("repeat", message)
            return True
        else:
            return False

    def set_play_on_load(self, message: bool) -> bool:
        self.state.update("play_on_load", message)
        return True

    # Show Plan Related Methods
    def get_plan(self, message: int):
        plan = sync(self.api.get_showplan(message))
        self.clear_channel_plan()
        channel = self.state.get()["channel"]
        self.logger.log.info(plan)
        if len(plan) > channel:
            for plan_item in plan[str(channel)]:
                try:
                    self.add_to_plan(plan_item)
                except Exception as e:
                    self.logger.log.critical(
                        "Failed to add item to show plan: {}".format(e)
                    )
                    continue

        return True

    def _check_ghosts(self, item: PlanItem):
        if isinstance(item.timeslotitemid, str) and item.timeslotitemid.startswith("I"):
            # Kinda a bodge for the moment, each "Ghost" (item which is not saved in the database showplan yet) needs to have a unique temporary item.
            # To do this, we'll start with the channel number the item was originally added to (to stop items somehow simultaneously added to different channels from having the same id)
            # And chuck in the unix epoch in ns for good measure.
            item.timeslotitemid = "GHOST-{}-{}".format(self.state.get()["channel"], time.time_ns())
        return item

    def add_to_plan(self, new_item: Dict[str, Any]) -> bool:
        new_item_obj = PlanItem(new_item)
        new_item_obj = self._check_ghosts(new_item_obj)
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        # Shift any plan items after the new position down one to make space.
        for item in plan_copy:
            if item.weight >= new_item_obj.weight:
                item.weight += 1

        plan_copy += [new_item_obj]  # Add the new item.

        plan_copy = self._fix_weights(plan_copy)

        self.state.update("show_plan", plan_copy)
        return True

    def remove_from_plan(self, weight: int) -> bool:
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        found = False
        for i in plan_copy:
            if i.weight == weight:
                plan_copy.remove(i)
                found = True
        if found:
            plan_copy = self._fix_weights(plan_copy)
            self.state.update("show_plan", plan_copy)
            return True
        return False

    def clear_channel_plan(self) -> bool:
        self.state.update("show_plan", [])
        return True

    def load(self, weight: int):
        if not self.isPlaying:
            self.unload()

            showplan = self.state.get()["show_plan"]

            loaded_item: Optional[PlanItem] = None

            for i in range(len(showplan)):
                if showplan[i].weight == weight:
                    loaded_item = showplan[i]
                    break

            if loaded_item is None:
                self.logger.log.error(
                    "Failed to find weight: {}".format(weight))
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

            if reload:
                loaded_item.filename = sync(self.api.get_filename(item=loaded_item))

            if not loaded_item.filename:
                return False

            self.state.update("loaded_item", loaded_item)

            for i in range(len(showplan)):
                if showplan[i].weight == weight:
                    self.state.update("show_plan", index=i, value=loaded_item)
                break
                # TODO: Update the show plan filenames???

            try:
                self.logger.log.info("Loading file: " +
                                     str(loaded_item.filename))
                mixer.music.load(loaded_item.filename)
            except Exception:
                # We couldn't load that file.
                self.logger.log.exception(
                    "Couldn't load file: " + str(loaded_item.filename)
                )
                return False

            try:
                if ".mp3" in loaded_item.filename:
                    song = MP3(loaded_item.filename)
                    self.state.update("length", song.info.length)
                else:
                    self.state.update(
                        "length", mixer.Sound(
                            loaded_item.filename).get_length() / 1000
                    )
            except Exception:
                self.logger.log.exception(
                    "Failed to update the length of item.")
                return False

            if loaded_item.cue > 0:
                self.seek(loaded_item.cue)
            else:
                self.seek(0)

            if self.state.get()["play_on_load"]:
                self.play()

        return True

    def unload(self):
        if not self.isPlaying:
            try:
                mixer.music.unload()
                self.state.update("paused", False)
                self.state.update("loaded_item", None)
            except Exception:
                self.logger.log.exception("Failed to unload channel.")
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

    def output(self, name: Optional[str] = None):
        wasPlaying = self.state.get()["playing"]

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
            self.load(loadedItem.weight)
        if wasPlaying:
            self.unpause()

        return True

    # Timeslotitemid can be a ghost (un-submitted item), so may be "IXXX"
    def set_marker(self, timeslotitemid: str, marker_str: str):
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
                self.logger.log.error("Failed to tracklist {}".format(loaded_item.name))
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
        self._potentially_end_tracklist()

        loaded_item = self.state.get()["loaded_item"]

        if not loaded_item:
            return

        # Track has ended
        print("Finished", loaded_item.name, loaded_item.weight)

        # Repeat 1
        # TODO ENUM
        if self.state.get()["repeat"] == "one":
            self.play()
            return

        loaded_new_item = False
        # Auto Advance
        if self.state.get()["auto_advance"]:
            for i in range(len(self.state.get()["show_plan"])):
                if self.state.get()["show_plan"][i].weight == loaded_item.weight:
                    if len(self.state.get()["show_plan"]) > i + 1:
                        self.load(self.state.get()["show_plan"][i + 1].weight)
                        loaded_new_item = True
                        break

                    # Repeat All
                    # TODO ENUM
                    elif self.state.get()["repeat"] == "all":
                        self.load(self.state.get()["show_plan"][0].weight)
                        loaded_new_item = True
                        break

        # Play on Load
        if self.state.get()["play_on_load"] and loaded_new_item:
            self.play()
            return

        # No automations, just stop playing.
        self.stop()
        if self.out_q:
            self._retAll("STOPPED")  # Tell clients that we've stopped playing.

    def _updateState(self, pos: Optional[float] = None):

        self.state.update("initialised", self.isInit)
        if self.isInit:
            if pos is not None:
                # Seeking sets the position like this when not playing.
                self.state.update("pos", pos)  # Reset back to 0 if stopped.
                self.state.update("pos_offset", 0)
            elif self.isPlaying:
                # This is the bit that makes the time actually progress during playback.
                # Get one last update in, incase we're about to pause/stop it.
                self.state.update("pos", max(0, mixer.music.get_pos() / 1000))

            # If the state is changing from playing to not playing, and the user didn't stop it, the item must have ended.
            if (
                self.state.get()["playing"]
                and not self.isPlaying
                and not self.stopped_manually
            ):
                self._ended()

            self.state.update("playing", self.isPlaying)
            self.state.update("loaded", self.isLoaded)

            self.state.update(
                "pos_true",
                min(
                    self.state.get()["length"],
                    self.state.get()["pos"] + self.state.get()["pos_offset"],
                ),
            )

            self.state.update(
                "remaining",
                max(0, (self.state.get()["length"] -
                    self.state.get()["pos_true"])),
            )

    def _ping_times(self):

        UPDATES_FREQ_SECS = 0.2
        if (
            self.last_time_update is None
            or self.last_time_update + UPDATES_FREQ_SECS < time.time()
        ):
            self.last_time_update = time.time()
            self._retAll("POS:" + str(self.state.get()["pos_true"]))

    def _retAll(self, msg):
        self.out_q.put("ALL:" + msg)

    def _retMsg(
        self, msg: Any, okay_str: bool = False, custom_prefix: Optional[str] = None
    ):
        # Make sure to add the message source back, so that it can be sent to the correct destination in the main server.
        if custom_prefix:
            response = custom_prefix
        else:
            response = "{}:{}:".format(self.last_msg_source, self.last_msg)
        if msg is True:
            response += "OKAY"
        elif isinstance(msg, str):
            if okay_str:
                response += "OKAY:" + msg
            else:
                response += "FAIL:" + msg
        else:
            response += "FAIL"
        self.logger.log.debug(("Preparing to send: {}".format(response)))
        if self.out_q:
            self.logger.log.debug(("Sending: {}".format(response)))
            self.out_q.put(response)

    def _send_status(self):
        # TODO This is hacky
        self._retMsg(str(self.status), okay_str=True,
                     custom_prefix="ALL:STATUS:")

    def _fix_weights(self, plan):
        def _sort_weight(e: PlanItem):
            return e.weight

        for item in plan:
            self.logger.log.info("Pre weights:\n{}".format(item))
        plan.sort(key=_sort_weight)  # Sort into weighted order.

        for item in plan:
            self.logger.log.info("Post Sort:\n{}".format(item))

        for i in range(len(plan)):
            plan[i].weight = i  # Recorrect the weights on the channel.

        for item in plan:
            self.logger.log.info("Post Weights:\n{}".format(item))
        return plan

    def __init__(
        self, channel: int, in_q: multiprocessing.Queue, out_q: multiprocessing.Queue, server_state: StateManager
    ):

        process_title = "Player: Channel " + str(channel)
        setproctitle.setproctitle(process_title)
        multiprocessing.current_process().name = process_title

        self.running = True
        self.out_q = out_q

        self.logger = LoggingManager("Player" + str(channel))

        self.api = MyRadioAPI(self.logger, server_state)

        self.state = StateManager(
            "Player" + str(channel),
            self.logger,
            self.__default_state,
            self.__rate_limited_params,
        )

        self.state.add_callback(self._send_status)

        self.state.update("channel", channel)
        self.state.update("tracklist_mode", server_state.get()["tracklist_mode"])

        # Just in case there's any weights somehow messed up, let's fix them.
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        plan_copy = self._fix_weights(plan_copy)
        self.state.update("show_plan", plan_copy)

        loaded_state = copy.copy(self.state.state)

        if loaded_state["output"]:
            self.logger.log.info("Setting output to: " +
                                 str(loaded_state["output"]))
            self.output(loaded_state["output"])
        else:
            self.logger.log.info("Using default output device.")
            self.output()

        loaded_item = loaded_state["loaded_item"]
        if loaded_item:
            self.logger.log.info("Loading filename: " +
                                 str(loaded_item.filename))
            self.load(loaded_item.weight)

            # Load may jump to the cue point, as it would do on a regular load.
            # If we were at a different state before, we have to override it now.
            if loaded_state["pos_true"] != 0:
                self.logger.log.info(
                    "Seeking to pos_true: " + str(loaded_state["pos_true"])
                )
                self.seek(loaded_state["pos_true"])

            if loaded_state["playing"] is True:
                self.logger.log.info("Resuming.")
                self.unpause()  # Use un-pause as we don't want to jump to a new position.
        else:
            self.logger.log.info("No file was previously loaded.")

        try:
            while self.running:
                time.sleep(0.02)
                self._updateState()
                self._ping_times()
                try:
                    message = in_q.get_nowait()
                    source = message.split(":")[0]
                    if source not in VALID_MESSAGE_SOURCES:
                        self.last_msg_source = ""
                        self.last_msg = ""
                        self.logger.log.warn(
                            "Message from unknown sender source: {}".format(
                                source)
                        )
                        continue

                    self.last_msg_source = source
                    self.last_msg = message.split(":", 1)[1]

                    self.logger.log.debug(
                        "Recieved message from source {}: {}".format(
                            self.last_msg_source, self.last_msg
                        )
                    )
                except Empty:
                    # The incomming message queue was empty,
                    # skip message processing
                    pass
                else:

                    # We got a message.

                    # Output re-inits the mixer, so we can do this any time.
                    if self.last_msg.startswith("OUTPUT"):
                        split = self.last_msg.split(":")
                        self._retMsg(self.output(split[1]))

                    elif self.isInit:
                        message_types: Dict[
                            str, Callable[..., Any]
                        ] = {  # TODO Check Types
                            "STATUS": lambda: self._retMsg(self.status, True),
                            # Audio Playout
                            # Unpause, so we don't jump to 0, we play from the current pos.
                            "PLAY": lambda: self._retMsg(self.unpause()),
                            "PAUSE": lambda: self._retMsg(self.pause()),
                            "UNPAUSE": lambda: self._retMsg(self.unpause()),
                            "STOP": lambda: self._retMsg(self.stop(user_initiated=True)),
                            "SEEK": lambda: self._retMsg(
                                self.seek(float(self.last_msg.split(":")[1]))
                            ),
                            "AUTOADVANCE": lambda: self._retMsg(
                                self.set_auto_advance(
                                    (self.last_msg.split(":")[1] == "True")
                                )
                            ),
                            "REPEAT": lambda: self._retMsg(
                                self.set_repeat(self.last_msg.split(":")[1])
                            ),
                            "PLAYONLOAD": lambda: self._retMsg(
                                self.set_play_on_load(
                                    (self.last_msg.split(":")[1] == "True")
                                )
                            ),
                            # Show Plan Items
                            "GET_PLAN": lambda: self._retMsg(
                                self.get_plan(int(self.last_msg.split(":")[1]))
                            ),
                            "LOAD": lambda: self._retMsg(
                                self.load(int(self.last_msg.split(":")[1]))
                            ),
                            "LOADED?": lambda: self._retMsg(self.isLoaded),
                            "UNLOAD": lambda: self._retMsg(self.unload()),
                            "ADD": lambda: self._retMsg(
                                self.add_to_plan(
                                    json.loads(
                                        ":".join(self.last_msg.split(":")[1:]))
                                )
                            ),
                            "REMOVE": lambda: self._retMsg(
                                self.remove_from_plan(
                                    int(self.last_msg.split(":")[1]))
                            ),
                            "CLEAR": lambda: self._retMsg(self.clear_channel_plan()),
                            "SETMARKER": lambda: self._retMsg(self.set_marker(self.last_msg.split(":")[1], self.last_msg.split(":", 2)[2])),
                        }

                        message_type: str = self.last_msg.split(":")[0]

                        if message_type in message_types.keys():
                            message_types[message_type]()

                        elif self.last_msg == "QUIT":
                            self._retMsg(True)
                            self.running = False
                            continue

                        else:
                            self._retMsg("Unknown Command")
                    else:

                        if self.last_msg == "STATUS":
                            self._retMsg(self.status)
                        else:
                            self._retMsg(False)

        # Catch the player being killed externally.
        except KeyboardInterrupt:
            self.logger.log.info("Received KeyboardInterupt")
        except SystemExit:
            self.logger.log.info("Received SystemExit")
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected Exception: {}".format(e))

        self.logger.log.info("Quiting player " + str(channel))
        self.quit()
        self._retAll("QUIT")
        del self.logger
        os._exit(0)


if __name__ == "__main__":
    raise Exception(
        "This BAPSicle Player is a subcomponenet, it will not run individually."
    )
