"""
    BAPSicle Server
    Next-gen audio playout server for University Radio York playout,
    based on WebStudio interface.

    Channel, holds a list of items and coordinates player elements to play them.

    Authors:
        Matthew Stratford
        Michael Grace

    Date:
        October, November 2020
"""

import os

from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time
from typing import Any, Callable, Dict, List, Optional
from syncer import sync
from threading import Timer

from helpers.myradio_api import MyRadioAPI
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from baps_types.plan import PlanItem
from baps_types.marker import Marker
import package

# TODO ENUM
VALID_MESSAGE_SOURCES = ["WEBSOCKET", "UI", "CONTROLLER", "TEST", "ALL"]
TRACKLISTING_DELAYED_S = 20


class Channel:
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

    # This is separate so we can use these default values to reset the default state if no players are present.
    __default_state_primary_player = {
        # These will be filled in from the values in the player_states entry for the player with ID "player_primary_id"
        # This is useful for showing in the UI etc.
        "loaded_item": None, # PlanItem of the current audio item to play.
        "playing": False,
        "paused": False,
        "cued": False, # Is the player at a cue point?
        "loaded": False, # Is the file in memory, ready to play instantly?
        "pos_elapsed": 0, # Time elapsed (secs) since starting current playback. This is pygame's position. WARN: It resets to 0 ever seek.
        "pos_offset": 0, # The difference (secs) between the pos_elapsed and the actual position in the file being played.
        "pos": 0, # The real amount of secs through the file we actually are. (pos = pos_elapsed + pos_offset)
        "remaining": 0, # Number of secs remaining of the file.
        "length": 0, # Length of file in secs.
    }

    __default_state = {
        "channel": -1,
        "player_states": [], # A list of players that are running under this channel, with their individual statuses.
        # Primary player state (see default state of player.py for expected contents)
        "player_primary_id": -1, # The ID number of the currently "primary" player. (i.e. the one that is playing / next to be played on a channel)

        # Channel settings, this will affect/represent all player instances.
        "auto_advance": True,
        "repeat": "none",  # none, one or all
        "play_on_load": False,
        "output": None,
        "show_plan": [],
        "tracklist_mode": "off",
        "tracklist_id": None,

    }

    # Append the player default state to the default state.
    __default_state.update(__default_state_primary_player)

    __rate_limited_params = ["pos_elapsed", "pos_offset", "pos", "remaining"]


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
        # TODO Passthru directly?
        return False

    def pause(self):
        # TODO Passthru directly?
        return False

    def unpause(self):
        # TODO Passthru directly?
        return False

    def stop(self, user_initiated: bool = False):
        # TODO Passthru directly?
        return False

    def seek(self, pos: float) -> bool:
        # TODO Passthru directly?
        return False

    def set_auto_advance(self, message: bool) -> bool:
        self.state.update("auto_advance", message)
        # TODO: Send message to player
        return True

    def set_repeat(self, message: str) -> bool:
        if message in ["all", "one", "none"]:
            self.state.update("repeat", message)

            # TODO Send to player

            return True
        else:
            return False

    def set_play_on_load(self, message: bool) -> bool:

        # TODO Send to player?
        self.state.update("play_on_load", message)
        return True



    # Show Plan Related Methods

    def get_plan(self, message: int):
        plan = sync(self.api.get_showplan(message))
        self.clear_channel_plan()
        channel = self.state.get()["channel"]
        self.logger.log.debug(plan)
        if not isinstance(plan, dict):
            return False
        if str(channel) in plan.keys():
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

    # TODO Allow just moving an item inside the channel instead of removing and adding.
    def add_to_plan(self, new_item: Dict[str, Any]) -> bool:
        new_item_obj = PlanItem(new_item)
        new_item_obj = self._check_ghosts(new_item_obj)
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        # Shift any plan items after the new position down one to make space.
        for item in plan_copy:
            if item.weight >= new_item_obj.weight:
                item.weight += 1

        plan_copy += [new_item_obj]  # Add the new item.

        self._fix_and_update_weights(plan_copy)


        loaded_item = self.state.get()["loaded_item"]
        if loaded_item:

            # Right. So this may be confusing.
            # So... If the user has just moved the loaded item in the channel (by removing above and readding)
            # Then we want to re-associate the loaded_item object reference with the new one.
            # The loaded item object before this change is now an ophan, which was kept around while the loaded item was potentially moved to another channel.
            if loaded_item.timeslotitemid == new_item_obj.timeslotitemid:
                self.state.update("loaded_item", new_item_obj)

            # NOPE NOPE NOPE
            # THIS IS AN EXAMPLE OF WHAT NOT TO DO!
            # ONCE AGAIN, THE LOADED ITEM IS THE SAME OBJECT INSTANCE AS THE ONE IN THE SHOW PLAN (AS LONG AS IT HASN'T BEEN RE/MOVED)

            ##    loaded_item.weight = new_item_obj.weight

            # Bump the loaded_item's weight if we just added a new item above it.
            ##elif loaded_item.weight >= new_item_obj.weight:
            ##    loaded_item.weight += 1

            # Else, new weight stays the same.
            ##else:
            ##    return True

            ##self.state.update("loaded_item", loaded_item)

        return True

    def remove_from_plan(self, weight: int) -> bool:
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        found: Optional[PlanItem ] = None

        before = []
        for item in plan_copy:
            before += (item.weight, item.name)

        self.logger.log.debug("Weights before removing weight {}:\n{}".format(weight, before))

        for i in plan_copy:
            if i.weight == weight:
                found = i
                plan_copy.remove(i)

        if found:
            self._fix_and_update_weights(plan_copy)

            # If we removed the loaded item from this channel, update it's weight
            # So we know how/not to autoadvance.
            loaded_item = self.state.get()["loaded_item"]
            if loaded_item == found:
                # Loaded_item is actually the same PlanItem instance as in the show_plan.
                # So if it's still in the show plan, we'll have corrected it's weight already.
                # If it was removed above, fix_weights won't have done anything
                # So we'll want to update the weight.

                # We're removing the loaded item from the channel.
                #if loaded_item.weight == weight:
                    loaded_item.weight = -1



                # If loaded_item wasn't the same instance, we'd want to do the below.

                # We removed an item above it. Shift it up.
                #elif loaded_item.weight > weight:
                #    loaded_item.weight -= 1
                # Else, new weight stays the same.
                #else:
                #    return True

                    self.state.update("loaded_item", loaded_item)
            return True
        return False

    def clear_channel_plan(self) -> bool:
        self.state.update("show_plan", [])
        return True

    def load(self, weight: int):
        return
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

        return
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
            self.logger.log.info("Quit mixer.")
        except Exception:
            self.logger.log.exception("Failed to quit mixer.")

    def output(self, name: Optional[str] = None):
        #TODO Passthrough direct?

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

    def reset_played(self, weight: int):
        plan: List[PlanItem] = self.state.get()["show_plan"]
        if weight == -1:
            for item in plan:
                item.play_count_reset()
            self.state.update("show_plan", plan)
        elif len(plan) > weight:
            plan[weight].play_count_reset()
            self.state.update("show_plan", plan[weight], weight)
        else:
            return False
        return True


    # Helper functions

    def _ended(self):

        return

        state = self.state.get()

        loaded_item = state["loaded_item"]

        if not loaded_item:
            return

        # Track has ended
        self.logger.log.info("Playback ended of {}, weight {}:".format(loaded_item.name, loaded_item.weight))

        # Auto Advance
        if state["auto_advance"]:

            # Check for loaded item in show plan.
            # If it's been removed, weight will be -1.
            # Just stop in this case.
            if loaded_item.weight < 0:
                self.logger.log.debug("Loaded item is no longer in channel (weight {}), not auto advancing.".format(loaded_item.weight))
            else:
                self.logger.log.debug("Found current loaded item in this channel show plan. Auto Advancing.")

                # If there's another item after this one, load that.
                if len(state["show_plan"]) > loaded_item.weight+1:
                    self.load(loaded_item.weight+1)
                    return

                # Repeat All (Jump to top again)
                # TODO ENUM
                elif state["repeat"] == "all":
                    self.load(0) # Jump to the top.
                    return

        # No automations, just stop playing.
        self.stop()
        self._retAll("STOPPED")  # Tell clients that we've stopped playing.

    def _updateState(self, pos: Optional[float] = None):

        # If the state is changing from playing to not playing, and the user didn't stop it, the item must have ended.
        #if (
        #    self.state.get()["playing"]
        #    and not self.isPlaying
        #    and not self.stopped_manually
        #):
        #    self._ended()
        state = self.state.get()

        found = False
        for player_state in state["player_states"]:
            if player_state["id"] != state["player_primary_id"]:
                continue

            found = True
            # Let's update the channel state values with the primary player's state values.
            for key in self.__default_state_primary_player.keys():
                try:
                    state[key] = player_state[key]
                except KeyError as e:
                    self.logger.log.exception("Player state for primary player ({}) is missing key. Key Error: ({}".format(player_state["id"], e))

        # If the primary player is not found, reset all the main state values to their defaults
        if not found:
            state.update(self.__default_state_primary_player)


        # TODO: Check / replace this with correct .update()
        # Update the state with the new changes.
        self.state.state = copy.copy(state)

    def _retAll(self, msg):
        if self.out_q:
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

        if self.out_q:
            if ("STATUS:" not in response):
                # Don't fill logs with status pushes, it's a mess.
                self.logger.log.debug(("Sending: {}".format(response)))
            self.out_q.put(response)
        else:
            self.logger.log.exception("Message return Queue is missing!!!! Can't send message.")

    def _send_status(self):
        # TODO This is hacky
        self._retMsg(str(self.status), okay_str=True,
                     custom_prefix="ALL:STATUS:")

    def _fix_and_update_weights(self, plan):
        def _sort_weight(e: PlanItem):
            return e.weight

        before = []
        for item in plan:
            before += (item.weight, item.name)

        self.logger.log.debug("Weights before fixing:\n{}".format(before))


        plan.sort(key=_sort_weight)  # Sort into weighted order.

        sorted = []
        for item in plan:
            sorted += (item.weight, item.name)

        self.logger.log.debug("Weights after sorting:\n{}".format(sorted))

        for i in range(len(plan)):
            plan[i].weight = i  # Recorrect the weights on the channel.

        fixed = []
        for item in plan:
            fixed += (item.weight, item.name)

        self.logger.log.debug("Weights after sorting:\n{}".format(fixed))
        self.state.update("show_plan", plan)

    def __init__(
        self, channel: int, in_q: multiprocessing.Queue, out_q: multiprocessing.Queue, server_state: StateManager
    ):

        channel_name = "Channel" + str(channel)
        setproctitle.setproctitle(channel_name)
        multiprocessing.current_process().name = channel_name

        self.running = True
        self.out_q = out_q

        self.logger = LoggingManager(channel_name, debug=package.build_beta)

        self.api = MyRadioAPI(self.logger, server_state)

        self.state = StateManager(
            channel_name,
            self.logger,
            self.__default_state,
            self.__rate_limited_params,
        )

        self.state.add_callback(self._send_status)

        self.state.update("channel", channel)
        self.state.update("tracklist_mode", server_state.get()["tracklist_mode"])

        # Just in case there's any weights somehow messed up, let's fix them.
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        self._fix_and_update_weights(plan_copy)

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
            # No need to load on init, the output switch does this, as it would for regular output switching.
            #self.load(loaded_item.weight)

            # Load may jump to the cue point, as it would do on a regular load.
            # If we were at a different state before, we have to override it now.
            if loaded_state["pos"] != 0:
                self.logger.log.info(
                    "Seeking to pos_true: " + str(loaded_state["pos"])
                )
                self.seek(loaded_state["pos"])

            if loaded_state["playing"] is True:
                self.logger.log.info("Resuming playback on init.")
                self.unpause()  # Use un-pause as we don't want to jump to a new position.
        else:
            self.logger.log.info("No file was previously loaded to resume.")

        try:
            while self.running:
                time.sleep(0.02)
                self._updateState()
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
                    split = self.last_msg.split(":")

                    message_types: Dict[
                        str, Callable[..., Any]
                    ] = {  # TODO Check Types
                        "STATUS": lambda: self._retMsg(self.status, True),
                        # Audio Playout
                        # Unpause, so we don't jump to 0, we play from the current pos.
                        "PLAY": lambda: self._retMsg(self.unpause()),
                        "PAUSE": lambda: self._retMsg(self.pause()),
                        #"PLAYPAUSE": lambda: self._retMsg(self.unpause() if not self.isPlaying else self.pause()), # For the hardware controller.
                        "UNPAUSE": lambda: self._retMsg(self.unpause()),
                        "STOP": lambda: self._retMsg(self.stop(user_initiated=True)),
                        "SEEK": lambda: self._retMsg(
                            self.seek(float(self.last_msg.split(":")[1]))
                        ),
                        "AUTOADVANCE": lambda: self._retMsg(
                            self.set_auto_advance(
                                (split[1] == "True")
                            )
                        ),
                        "REPEAT": lambda: self._retMsg(
                            self.set_repeat(split[1])
                        ),
                        "PLAYONLOAD": lambda: self._retMsg(
                            self.set_play_on_load(
                                (split[1] == "True")
                            )
                        ),
                        # Show Plan Items
                        "GET_PLAN": lambda: self._retMsg(
                            self.get_plan(int(split[1]))
                        ),
                        "LOAD": lambda: self._retMsg(
                            self.load(int(split[1]))
                        ),
                        #"LOADED?": lambda: self._retMsg(self.isLoaded),
                        "UNLOAD": lambda: self._retMsg(self.unload()),
                        "OUTPUT": lambda: self._retMsg(self.output(split[1])),
                        "ADD": lambda: self._retMsg(
                            self.add_to_plan(
                                json.loads(
                                    ":".join(split[1:]))
                            )
                        ),
                        "REMOVE": lambda: self._retMsg(
                            self.remove_from_plan(
                                int(split[1]))
                        ),
                        "CLEAR": lambda: self._retMsg(self.clear_channel_plan()),
                        "SETMARKER": lambda: self._retMsg(self.set_marker(split[1], self.last_msg.split(":", 2)[2])),
                        "RESETPLAYED": lambda: self._retMsg(self.reset_played(int(split[1]))),

                    }

                    message_type: str = split[0]

                    if message_type in message_types.keys():
                        message_types[message_type]()

                    elif self.last_msg == "QUIT":
                        self._retMsg(True)
                        self.running = False
                        continue

                    else:
                        self._retMsg("Unknown Command")

        # Catch the channel being killed externally.
        except KeyboardInterrupt:
            self.logger.log.info("Received KeyboardInterupt")
        except SystemExit:
            self.logger.log.info("Received SystemExit")
        except Exception as e:
            self.logger.log.exception(
                "Received unexpected Exception: {}".format(e))

        self.logger.log.info("Quiting channel " + str(channel))
        self.quit()
        self._retAll("QUIT")
        del self.logger
        os._exit(0)


if __name__ == "__main__":
    raise Exception(
        "This BAPSicle Channel is a subcomponenet, it will not run individually."
    )
