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

from player import Player
from helpers.myradio_api import MyRadioAPI
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from baps_types.plan import PlanItem, PlanItemEncoder
from baps_types.marker import Marker
from helpers.messages import encode_msg_dict, encode_msg_new, decode_msg
import package

# TODO ENUM
VALID_MESSAGE_SOURCES = ["WEBSOCKET", "UI", "CONTROLLER", "TEST", "ALL"]


class Channel:
    out_q: multiprocessing.Queue
    last_msg: str
    last_msg_source: str
    last_time_update = None

    state: StateManager
    logger: LoggingManager
    api: MyRadioAPI

    server_state: StateManager

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
        "player_states": {}, # A list of players that are running under this channel, with their individual statuses.
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

    player_processes: Dict[int,multiprocessing.Process] = {} # These must be strings because
    player_to_q: Dict[int,multiprocessing.Queue] = {}
    player_from_q: Dict[int,multiprocessing.Queue] = {}


    @property
    def isInit(self):
        return self.state.state["initialised"]

    @property
    def isPlaying(self) -> bool:
        return self.state.state["playing"]

    @property
    def isPaused(self) -> bool:
        return self.state.state["paused"]

    @property
    def isLoaded(self):
        return self.state.state["loaded"]

    @property
    def isCued(self):
        return self.state.state["cued"]

    @property
    def status(self):
        state = copy.copy(self.state.state)

        # Convert any PlanItems into their dict equiv.
        res = json.dumps(state, cls=PlanItemEncoder)
        return res

    # Audio Player Instance Related Methods

    def _send_to_player(self, id:int = -1, msg:str = ""):
        if id == -1:
            id = self.state.state["player_primary_id"]
        if id in self.player_to_q and msg:
            self.player_to_q[id].put(msg)

#    def _player_primary_passthru(self, msg: dict):
#        # TODO Return back reply status somehow?
#        encoded = encode_msg_dict(msg)
#        self._send_to_player(msg=encoded)

    def play(self):
        # TODO Multiplayer logic here

        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="PLAY"))
        return False

    def pause(self):
        # TODO Multiplayer logic here
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="PAUSE"))
        return False

    def unpause(self):
        # TODO Multiplayer logic here
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="UNPAUSE"))
        return False

    def stop(self):
        # TODO Multiplayer logic here
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="STOP"))
        return False

    def seek(self, pos: float) -> bool:
        # TODO Multiplayer logic here
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="SEEK", extra={"pos":pos}))
        return False

    def set_auto_advance(self, message: bool) -> bool:
        self.state.update("auto_advance", message)
        return True

    def set_repeat(self, message: str) -> bool:
        if message in ["all", "one", "none"]:
            self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="REPEAT", extra={"enabled": message == "one"}))
            self.state.update("repeat", message)
            return True
        else:
            return False

    def set_play_on_load(self, message: bool) -> bool:
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="PLAYONLOAD", extra={"enabled": message == "one"}))
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

            self.state.update("loaded_item", loaded_item)

            for i in range(len(showplan)):
                if showplan[i].weight == weight:
                    self.state.update("show_plan", index=i, value=loaded_item)
                break
                # TODO: Update the show plan filenames???

            self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="LOAD",extra=loaded_item.__dict__))

        return False

    def unload(self):
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="UNLOAD"))
        return False

    def quit(self):
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="QUIT"))
        return True

    def output(self, name: Optional[str] = None):
        self._send_to_player(msg=encode_msg_new(src="CHANNEL",command="OUTPUT", extra={"name":name}))

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
        for player_state in state["player_states"].values():
            if int(player_state["id"]) != int(state["player_primary_id"]):
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

    def _player_init(self, id = -1):
        if id < 0:
            self.logger.log.exception("Invalid player id: " + str(id))
            return False

        if (id in self.player_processes.keys() and isinstance(self.player_processes[id], multiprocessing.Process)):
            self.logger.log.warning("Cannot init player id {}, already initialised.".format(id))
            return True

        channel = self.state.state["channel"]

        # Alright, let's start a player instance.
        self.player_to_q[id] = multiprocessing.Queue()
        self.player_from_q[id] = multiprocessing.Queue()
        self.player_processes[id] = multiprocessing.Process(
            target=Player, args=(channel, id, self.player_to_q[id], self.player_from_q[id], self.server_state)
        )
        self.player_processes[id].start()
        self.logger.log.info("Started player {}".format(id))

        return


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

    def _handle_player_responses(self):
        for player_id in self.player_from_q.keys():
            player_id = int(player_id)
            if self.player_from_q[player_id]:
                try:
                    msg_encoded = self.player_from_q[player_id].get_nowait()
                except Empty:
                    # The incomming message queue was empty,
                    # skip message processing
                    continue

                msg = decode_msg(msg_encoded)

                if msg["command"] == "STATUS":
                    if msg["status"] == True:
                        print(msg["extra"])
                        player_states:dict = self.state.get()["player_states"]

                        state = msg["extra"]
                        state["loaded_item"] = PlanItem(state["loaded_item"]) if state["loaded_item"] else None


                        player_states[str(player_id)] = state
                        self.state.update("player_states", player_states)



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

        self.server_state = server_state

        self.state.add_callback(self._send_status)

        self.state.update("channel", channel)
        self.state.update("tracklist_mode", server_state.get()["tracklist_mode"])

        # Just in case there's any weights somehow messed up, let's fix them.
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        self._fix_and_update_weights(plan_copy)

        #loaded_state = copy.copy(self.state.state)

        # Init the first player.
        self._player_init(id=0)

        self.state.update("player_primary_id", 0)


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
                        "PLAY": lambda: self._retMsg(self.play()),
                        "PAUSE": lambda: self._retMsg(self.pause()),
                        #"PLAYPAUSE": lambda: self._retMsg(self.unpause() if not self.isPlaying else self.pause()), # For the hardware controller.
                        "UNPAUSE": lambda: self._retMsg(self.unpause()),
                        "STOP": lambda: self._retMsg(self.stop()),
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

                self._handle_player_responses()
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
