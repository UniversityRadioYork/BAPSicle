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

# This is the player. It does everything regarding playing sound.
# Reliability is critical here, so we're catching literally every exception possible and handling it.

# It is key that whenever the clients tells us to do something
# that we respond with something, FAIL or OKAY. They don't like to be kept waiting/ignored.

# Stop the Pygame Hello message.
import os
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
from helpers.os_environment import isLinux
# It's the only one we could get to work.
if isLinux():
    os.putenv('SDL_AUDIODRIVER', 'pulseaudio')

from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time
from typing import Any, Callable, Dict, List, Optional
from pygame import mixer, error
from mutagen.mp3 import MP3
from syncer import sync
from threading import Timer
from datetime import datetime

from helpers.normalisation import get_normalised_filename_if_available, get_original_filename_from_normalised
from helpers.myradio_api import MyRadioAPI
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager
from baps_types.plan import PlanItem
from baps_types.marker import Marker
import package

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

    # The default state that should be set if there is no previous state info.
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
        "live": True,
        "tracklist_mode": "off",
        "tracklist_id": None,
    }

    # These tell the StateManager which variables we don't care about really accurate history for.
    # This means that the internal running state of the player will have quickly updating info (multiple times a sec)
    # But we will rate limit (a few secs) saving updates to these variables to the state JSON file.
    __rate_limited_params = ["pos", "pos_offset", "pos_true", "remaining"]

    # Checks if the mixer is init'd. It will throw an exception if not.
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
            return not self.isPaused and mixer.music.get_busy()
        return False

    @property
    def isPaused(self) -> bool:
        return self.state.get()["paused"]

    @property
    def isLoaded(self):
        return self.state.get()["loaded"]

    # Checks if a file has been loaded
    # This should be run with a long test before client requests for status etc.
    # Short tests are used in other logic in the player, without fussing over full playback tests.
    def _checkIsLoaded(self, short_test: bool = False):

        loaded = True

        if not self.state.get()["loaded_item"] or not self.isInit:
            loaded = False
        elif not self.isPlaying:
            # Because this function can be called very often, only some (less frequent) checks will initiate a full trial of loading success, for efficiency.
            if not short_test:
                # We're not playing now, so we can quickly test run
                # If that works, we're truely loaded.
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
                    loaded = False
                finally:
                    mixer.music.stop()

                mixer.music.set_volume(1)

        self.state.update("loaded", loaded)
        return loaded

    # Is the player at a cue marker point?
    @property
    def isCued(self):
        if not self.isLoaded:
            return False
        return (
            self.state.get()["pos_true"] == self.state.get()["loaded_item"].cue
            and not self.isPlaying
        )

    # Returns the state of the player as a nice friendly JSON dump.
    @property
    def status(self):
        # Get a copy of the server state.
        state = self.state.state

        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        # Convert objects to a nice JSON friendly dicts.
        state["loaded_item"] = (
            state["loaded_item"].__dict__ if state["loaded_item"] else None
        )
        state["show_plan"] = [repr.__dict__ for repr in state["show_plan"]]

        res = json.dumps(state)
        return res

    # Audio Playout Related Methods


    # Loads a plan item into the player, ready for playing.
    # This includes some retry logic to try and double-down on ensuring it plays successfully.
    def load(self, weight: int):
        if not self.isPlaying:
            # If we have something loaded already, unload it first.
            self.unload()

            loaded_state = self.state.get()

            # Sometimes (at least on windows), the pygame player will lose output to the sound output after a while.
            # It's odd, but essentially, to stop / recover from this, we de-init the pygame mixer and init it again.
            self.logger.log.info(
                "Resetting output (in case of sound output gone silent somehow) to "
                + str(loaded_state["output"])
            )
            self.set_output(loaded_state["output"])

            showplan = loaded_state["show_plan"]

            loaded_item: Optional[PlanItem] = None

            # Go find the show plan item of the weight we've been asked to load.
            for i in range(len(showplan)):
                if showplan[i].weight == weight:
                    loaded_item = showplan[i]
                    break

            # If we didn't find it, exit.
            if loaded_item is None:
                self.logger.log.error(
                    "Failed to find weight: {}".format(weight))
                return False

            # This item exists, so we're comitting to load this item.
            self.state.update("loaded_item", loaded_item)

            # The file_manager helper may have pre-downloaded the file already, or we've played it before.
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

            # Ask the API for the file if we need it.
            if reload:
                file = sync(self.api.get_filename(item=loaded_item))
                loaded_item.filename = str(file) if file else None

            # If the API still couldn't get the file, RIP.
            if not loaded_item.filename:
                return False

            # Swap with a normalised version if it's ready, else returns original.
            loaded_item.filename = get_normalised_filename_if_available(
                loaded_item.filename
            )

            # Given we've just messed around with filenames etc, update the item again.
            self.state.update("loaded_item", loaded_item)
            for i in range(len(showplan)):
                if showplan[i].weight == weight:
                    self.state.update("show_plan", index=i, value=loaded_item)
                break

            load_attempt = 0

            # Let's have 5 attempts at loading the item audio
            while load_attempt < 5:
                load_attempt += 1

                original_file = None
                if load_attempt == 3:
                    # Ok, we tried twice already to load the file.
                    # Let's see if we can recover from this.
                    # Try swapping the normalised version out for the original.
                    original_file = get_original_filename_from_normalised(
                        loaded_item.filename
                    )
                    self.logger.log.warning("3rd attempt. Trying the non-normalised file: {}".format(original_file))

                if load_attempt == 4:
                    # well, we've got so far that the normalised and original files didn't load.
                    # Take a last ditch effort to download the original file again.
                    file = sync(self.api.get_filename(item=loaded_item, redownload=True))
                    if file:
                        original_file = str(file)
                    self.logger.log.warning("4rd attempt. Trying to redownload the file, got: {}".format(original_file))

                if original_file:
                    loaded_item.filename = original_file

                try:
                    self.logger.log.info(
                        "Attempt {} Loading file: {}".format(load_attempt, loaded_item.filename))
                    mixer.music.load(loaded_item.filename)
                except Exception:
                    # We couldn't load that file.
                    self.logger.log.exception(
                        "Couldn't load file: " + str(loaded_item.filename)
                    )
                    continue  # Try loading again.

                try:
                    if loaded_item.filename.endswith(".mp3"):
                        song = MP3(loaded_item.filename)
                        self.state.update("length", song.info.length)
                    else:
                        # WARNING! Pygame / SDL can't seek .wav files :/
                        self.state.update(
                            "length",
                            mixer.Sound(
                                loaded_item.filename).get_length() / 1000,
                        )
                except Exception:
                    self.logger.log.exception(
                        "Failed to update the length of item.")
                    continue  # Try loading again.

                # Everything worked, we made it!
                # Write the loaded item again once more, to confirm the filename if we've reattempted.
                self.state.update("loaded_item", loaded_item)

                # Now just double check that pygame could actually play it (silently)
                self._checkIsLoaded()
                if not self.isLoaded:
                    self.logger.log.error(
                        "Pygame loaded file without error, but never actually loaded."
                    )
                    continue  # Try loading again.

                # If the track has a cue point, let's jump to that, ready.
                if loaded_item.cue > 0:
                    self.seek(loaded_item.cue)
                else:
                    self.seek(0)

                if loaded_state["play_on_load"]:
                    self.unpause()

                return True

            # Even though we failed, make sure state is up to date with latest failure.
            # We're comitting to load this item.
            self.state.update("loaded_item", loaded_item)
            self._checkIsLoaded()

        return False

    # Remove the currently loaded item from the player.
    # Not much reason to do this, but if it makes you happy.
    def unload(self):
        if not self.isPlaying:
            try:
                mixer.music.unload()
                self.state.update("paused", False)
                self.state.update("loaded_item", None)
            except Exception:
                self.logger.log.exception("Failed to unload channel.")
                return False

        #self._potentially_end_tracklist()
        # If we unloaded successfully, reset the tracklist_id, ready for the next item.
        if not self.isLoaded:
            self.state.update("tracklist_id", None)

        # If we successfully unloaded, this will return true, for success!
        return not self.isLoaded


    # Starts playing the loaded item, from a given position (secs)
    def play(self, pos: float = 0):
        self.logger.log.info("Playing from pos: " + str(pos))
        if not self.isLoaded:
            self.logger.log.warning("Player is not loaded.")
            return False
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

    # Pauses the player
    def pause(self):
        # Because the player's position is stored by a event from pygame while playing only,
        # the current playback position state will remain, in case we unpause later.
        try:
            mixer.music.stop()
        except Exception:
            self.logger.log.exception("Failed to pause.")
            return False

        self.stopped_manually = True
        self.state.update("paused", True)
        return True

    # Plays the player, from the playback position it was already at.
    def unpause(self):
        if not self.isPlaying:
            state = self.state.get()
            position: float = state["pos_true"]
            if not self.play(position):
                self.logger.log.exception(
                    "Failed to unpause from pos: " + str(position)
                )
                return False

            self.state.update("paused", False)

            # Increment Played count
            loaded_item = state["loaded_item"]
            if loaded_item:
                loaded_item.play_count_increment()
                self.state.update("loaded_item", loaded_item)

            return True
        return False

    # Stop the player.
    def stop(self, user_initiated: bool = False):
        try:
            mixer.music.stop()
        except Exception:
            self.logger.log.exception("Failed to stop playing.")
            return False
        self.state.update("paused", False)

        # When it wasn't _ended() calling this, end the tracklist.
        # _ended() already calls this, but user stops won't have.
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

    # Move the audio position (secs) of the player
    def seek(self, pos: float) -> bool:
        self.logger.log.info("Seeking to pos:" + str(pos))
        if self.isPlaying:
            # If we're playing, just start playing directly from that position
            try:
                self.play(pos)
            except Exception:
                self.logger.log.exception("Failed to seek to pos: " + str(pos))
                return False
            return True
        else:
            # If we're not actually playing at the moment, set the player to be paused at the new position
            self.logger.log.debug(
                "Not playing during seek, setting pos state for next play."
            )
            self.stopped_manually = True  # Don't trigger _ended() on seeking.
            if pos > 0:
                self.state.update("paused", True)
            self._updateState(pos=pos)
        return True

    # Set the output device name and initialise the pygame audio mixer.
    def set_output(self, name: Optional[str] = None):
        wasPlaying = self.isPlaying

        state = self.state.get()
        oldPos = state["pos_true"]

        name = None if (not name or name.lower() == "none") else name

        # Stop the mixer if it's already init'd.
        self.quit()
        self.state.update("output", name)
        try:
            # Setup the mixer.
            # Sample rate of 44100Hz (44.1KHz) (matching the MP3's and typical CD/online source material)
            # 16 bits per sample
            # 2 channels (stereo)
            # sample buffer of 1024 samples
            if name:
                mixer.init(44100, -16, 2, 1024, devicename=name)
            else:
                # Use the default system output
                mixer.init(44100, -16, 2, 1024)
        except Exception:
            self.logger.log.exception(
                "Failed to init mixer with device name: " + str(name)
            )
            return False

        # If we had something loaded before, load it back in and play it.
        loadedItem = state["loaded_item"]
        if loadedItem:
            self.logger.log.info("Reloading after output change.")
            self.load(loadedItem.weight)
        if wasPlaying:
            self.logger.log.info("Resuming playback after output change.")
            self.play(oldPos)

        return True

    # De-initialises the pygame mixer.
    def quit(self):
        try:
            mixer.quit()
            self.state.update("paused", False)
            self.logger.log.info("Quit mixer.")
        except Exception:
            self.logger.log.exception("Failed to quit mixer.")


    # Sets whether auto advance is on or off
    # Auto advance is where the next item in the list is selected after the current item is finished playing.
    def set_auto_advance(self, message: bool) -> bool:
        self.state.update("auto_advance", message)
        return True

    # As you'd expect, all rotates around all of the items in the channel plan, and loops to the first from the last.
    # One plays the same item over and over again
    def set_repeat(self, message: str) -> bool:
        if message in ["all", "one", "none"]:
            self.state.update("repeat", message)
            return True
        else:
            return False

    # Set whether the player should play the item as soon as it's been selected.
    def set_play_on_load(self, message: bool) -> bool:
        self.state.update("play_on_load", message)
        return True


    # Show Plan Related Methods

    def _check_ghosts(self, item: PlanItem):
        # Webstudio returns intermediate "I" objects when dragging in from the media sidebar.
        if isinstance(item.timeslotitemid, str) and item.timeslotitemid.startswith("I"):
            # Kinda a bodge for the moment, each "Ghost" (item which is not saved in the database showplan yet)
            # needs to have a unique temporary item.
            # To do this, we'll start with the channel number the item was originally added to
            # (to stop items somehow simultaneously added to different channels from having the same id)
            # And chuck in the unix epoch in ns for good measure.
            item.timeslotitemid = "GHOST-{}-{}".format(
                self.state.get()["channel"], time.time_ns()
            )
        return item

    # Pull in from the API the show plan items for this player channel.
    def get_plan(self, show_plan_id: int):
        # Call the API
        # sync turns the asyncronous API into syncronous.
        plan = sync(self.api.get_showplan(show_plan_id))

        # Empty the channel plan so we can put the updated items in.
        self.clear_channel_plan()
        channel = self.state.get()["channel"]
        self.logger.log.debug(plan)
        # If there isn't a show plan for the required show, return failure without filling in the plan.
        if not isinstance(plan, dict):
            return False

        # Add the items, if this channel has any.
        if str(channel) in plan.keys():
            plan_items = plan[str(channel)]
            try:
                self.add_to_plan(plan_items)
            except Exception as e:
                self.logger.log.error(
                    "Failed to add items to show plan: {}".format(e)
                )
                return False

        return True

    # Add a list of new show plan items to the channel.
    # These will be in dict format, we'll validate them and turn them into proper plan objects.
    # TODO Allow just moving an item inside the channel instead of removing and adding.
    def add_to_plan(self, new_items: List[Dict[str, Any]]) -> bool:
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])

        for new_item in new_items:
            new_item_obj = PlanItem(new_item)
            new_item_obj = self._check_ghosts(new_item_obj)

            # Shift any plan items after the new position down one to make space.
            for item in plan_copy:
                if item.weight >= new_item_obj.weight:
                    item.weight += 1

            plan_copy += [new_item_obj]  # Add the new item.

            loaded_item = self.state.get()["loaded_item"]
            if loaded_item:

                # Right. So this may be confusing.
                # So... If the user has just moved the loaded item in the channel (by removing above and readding)
                # Then we want to re-associate the loaded_item object reference with the new one.
                # The loaded item object before this change is now an orphan, which was
                # kept around while the loaded item was potentially moved to another
                # channel.
                if loaded_item.timeslotitemid == new_item_obj.timeslotitemid:
                    self.state.update("loaded_item", new_item_obj)

                # NOPE NOPE NOPE
                # THIS IS AN EXAMPLE OF WHAT NOT TO DO!
                # ONCE AGAIN, THE LOADED ITEM IS THE SAME OBJECT INSTANCE AS THE ONE IN
                # THE SHOW PLAN (AS LONG AS IT HASN'T BEEN RE/MOVED)

                #    loaded_item.weight = new_item_obj.weight

                # Bump the loaded_item's weight if we just added a new item above it.
                # elif loaded_item.weight >= new_item_obj.weight:
                #     loaded_item.weight += 1

                # Else, new weight stays the same.
                # else:
                #     return True

                # self.state.update("loaded_item", loaded_item)

        # Just in case somehow we've ended up with items with the same weights (or gaps)
        # We'll correct them.
        # This function also orders and saves the updated plan copy we've given it.
        self._fix_and_update_weights(plan_copy)

        return True

    # Removes an item from the show plan with the given weight (index)
    def remove_from_plan(self, weight: int) -> bool:
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        found: Optional[PlanItem] = None

        # Give some helpful debug
        before = []
        for item in plan_copy:
            before += (item.weight, item.name)

        self.logger.log.debug(
            "Weights before removing weight {}:\n{}".format(weight, before)
        )

        # Look for the item with the correct weight
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
                # if loaded_item.weight == weight:
                loaded_item.weight = -1

                # If loaded_item wasn't the same instance, we'd want to do the below.

                # We removed an item above it. Shift it up.
                # elif loaded_item.weight > weight:
                #    loaded_item.weight -= 1
                # Else, new weight stays the same.
                # else:
                #    return True

                self.state.update("loaded_item", loaded_item)
            return True
        return False

    # Empties the channel's plan.
    def clear_channel_plan(self) -> bool:
        self.state.update("show_plan", [])
        return True

    # PlanItems can have markers. These are essentially bookmarked positions in the audio.
    # Timeslotitemid can be a ghost (un-submitted item), so may be "IXXX", hence str.
    def set_marker(self, timeslotitemid: str, marker_str: str):
        set_loaded = False
        success = True
        try:
            # Take a string representation of the marker (from clients)
            marker = Marker(marker_str)
        except Exception as e:
            self.logger.log.error(
                "Failed to create Marker instance with {} {}: {}".format(
                    timeslotitemid, marker_str, e
                )
            )
            return False

        # Allow setting a marker for the currently loaded item.
        if timeslotitemid == "-1":
            set_loaded = True
            if not self.isLoaded:
                return False
            timeslotitemid = self.state.get()["loaded_item"].timeslotitemid
        elif (
            self.isLoaded
            and self.state.get()["loaded_item"].timeslotitemid == timeslotitemid
        ):
            set_loaded = True

        # Loop over the show plan items. When you find the timeslotitemid the marker is for, update it.
        # This is instead of weight, since the client asking doesn't know the weight of the item (or which channel it is)
        # So all channels will look and update if necessary.
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        for i in range(len(self.state.get()["show_plan"])):

            item = plan_copy[i]

            if str(item.timeslotitemid) == str(timeslotitemid):
                try:
                    new_item = item.set_marker(marker)
                    self.state.update("show_plan", new_item, index=i)

                except Exception as e:
                    self.logger.log.error(
                        "Failed to set marker on item {}: {} with marker \n{}".format(
                            timeslotitemid, e, marker
                        )
                    )
                    success = False

        # If the item to update was the loaded item, update it.
        if set_loaded:
            try:
                self.state.update(
                    "loaded_item", self.state.get(
                    )["loaded_item"].set_marker(marker)
                )
            except Exception as e:
                self.logger.log.error(
                    "Failed to set marker on loaded_item {}: {} with marker \n{}".format(
                        timeslotitemid, e, marker
                    )
                )
                success = False

        return success

    # This marks an item as played, or not.
    # A weight of -1 will affect all items in the channel
    def set_played(self, weight: int, played: bool):
        plan: List[PlanItem] = self.state.get()["show_plan"]
        if weight == -1:
            for item in plan:
                item.play_count_increment() if played else item.play_count_reset()
            self.state.update("show_plan", plan)
        elif len(plan) > weight:
            plan[weight].play_count_increment() if played else plan[
                weight
            ].play_count_reset()
            self.state.update("show_plan", plan[weight], weight)
        else:
            return False
        return True

    # Tells the player that the fader is live on-air, so it can tell tracklisting from PFL
    def set_live(self, live: bool):

        self.state.update("live", live)

        # If we're going to live (potentially from not live/PFL), potentially tracklist if it's playing.
        if live:
            self._potentially_tracklist()
        # If the fader is now not live, don't bother stopping the tracklist, incase it's faded up again during the same playback.
        return True

    # Helper functions

    # This essentially allows the tracklist start API call to happen in a separate thread, to avoid hanging playout/loading.
    def _potentially_tracklist(self):
        mode = self.state.get()["tracklist_mode"]

        time: int = -1
        if mode == "on":
            time = 0 # Let's do it pretty quickly.
        if mode == "fader-live":
            time = 4 # Give presenter a bit of a grace period in case they accidentally fade up the wrong one.
        elif mode == "delayed":
            # Let's do it in a bit, once we're sure it's been playing. (Useful if we've got no idea if it's live or cueing.)
            time = TRACKLISTING_DELAYED_S

        if time >= 0 and not self.tracklist_start_timer:
            self.logger.log.info(
                "Setting timer for tracklisting in {} secs due to Mode: {}".format(
                    time, mode
                )
            )
            self.tracklist_start_timer = Timer(time, self._tracklist_start)
            self.tracklist_start_timer.start()
        elif self.tracklist_start_timer:
            self.logger.log.error(
                "Failed to potentially tracklist, timer already busy."
            )

    # This essentially allows the tracklist end API call to happen in a separate thread, to avoid hanging playout/loading.
    def _potentially_end_tracklist(self):

        if self.tracklist_start_timer:
            self.logger.log.info(
                "A tracklist start timer was running, cancelling.")
            self.tracklist_start_timer.cancel()
            self.tracklist_start_timer = None

            # Decrement Played count on track we didn't play enough of to tracklist.
            state = self.state.get()
            loaded_item = state["loaded_item"]
            if loaded_item and loaded_item.type == "central":
                loaded_item.play_count_decrement()
                self.state.update("loaded_item", loaded_item)

        # Make a copy of the tracklist_id, it will get reset as we load the next item.
        tracklist_id = self.state.get()["tracklist_id"]
        if not tracklist_id:
            self.logger.log.info("No tracklist to end.")
            return

        if tracklist_id:
            self.logger.log.info(
                "Attempting to end tracklist_id '{}'".format(tracklist_id)
            )
            if self.tracklist_end_timer:
                self.logger.log.error(
                    "Failed to potentially end tracklist, timer already busy."
                )
                return
            self.state.update("tracklist_id", None)
            # This threads it, so it won't hang track loading if it fails.
            self.tracklist_end_timer = Timer(
                1, self._tracklist_end, [tracklist_id])
            self.tracklist_end_timer.start()
        else:
            self.logger.log.warning(
                "Failed to potentially end tracklist, no tracklist started."
            )

    # The actual function that will register with the API an item being played.
    def _tracklist_start(self):
        state = self.state.get()
        loaded_item = state["loaded_item"]
        if not loaded_item:
            self.logger.log.error(
                "Tried to call _tracklist_start() with no loaded item!"
            )

        elif not self.isPlaying:
            self.logger.log.info("Not tracklisting since not playing.")

        else:

            tracklist_id = state["tracklist_id"]
            if not tracklist_id:
                if state["tracklist_mode"] == "fader-live" and not state["live"]:
                    self.logger.log.info(
                        "Not tracklisting since fader is not live.")
                else:
                    self.logger.log.info(
                        "Tracklisting item: '{}'".format(loaded_item.name)
                    )
                    tracklist_id = self.api.post_tracklist_start(loaded_item)
                    if not tracklist_id:
                        self.logger.log.warning(
                            "Failed to tracklist '{}'".format(loaded_item.name)
                        )
                    else:
                        self.logger.log.info(
                            "Tracklist id: '{}'".format(tracklist_id))
                        self.state.update("tracklist_id", tracklist_id)
            else:
                self.logger.log.info(
                    "Not tracklisting item '{}', already got tracklistid: '{}'".format(
                        loaded_item.name, tracklist_id
                    )
                )

        # No matter what we end up doing, we need to kill this timer so future ones can run.
        self.tracklist_start_timer = None

    # The actual function that will register with the API an item being finished playing.
    def _tracklist_end(self, tracklist_id):

        if tracklist_id:
            self.logger.log.info(
                "Attempting to end tracklist_id '{}'".format(tracklist_id)
            )
            self.api.post_tracklist_end(tracklist_id)
        else:
            self.logger.log.error(
                "Tracklist_id to _tracklist_end() missing. Failed to end tracklist."
            )

        # No matter what we end up doing, we need to kill this timer so future ones can run.
        self.tracklist_end_timer = None

    # When an item has ended (the pygame mixer has told us that it has stopped playing)
    def _ended(self):
        self._potentially_end_tracklist()

        state = self.state.get()

        loaded_item = state["loaded_item"]

        if not loaded_item:
            return

        # Track has ended
        self.logger.log.info(
            "Playback ended of {}, weight {}:".format(
                loaded_item.name, loaded_item.weight
            )
        )
        # Just make sure that if we stop and do nothing, we end up at 0.
        self.state.update("pos", 0)

        # Repeat 1? Spin that record again!
        # TODO ENUM
        if state["repeat"] == "one":
            self.play()
            return

        # Auto Advance
        if state["auto_advance"]:

            # Check for loaded item in show plan.
            # If it's been removed, weight will be -1.
            # Just stop in this case.
            if loaded_item.weight < 0:
                self.logger.log.debug(
                    "Loaded item is no longer in channel (weight {}), not auto advancing.".format(
                        loaded_item.weight
                    )
                )
            else:
                self.logger.log.debug(
                    "Found current loaded item in this channel show plan. Auto Advancing."
                )

                # If there's another item after this one, load that.
                if len(state["show_plan"]) > loaded_item.weight + 1:
                    self.load(loaded_item.weight + 1)
                    return

                # Repeat All (Jump to top again)
                # TODO ENUM
                elif state["repeat"] == "all":
                    self.load(0)  # Jump to the top.
                    return

        # No automations, just stop playing.
        self.stop()
        self._retAll("STOPPED")  # Tell clients that we've stopped playing.

    # This runs every main loop, to update anything that changes often / automatically.
    def _updateState(self, pos: Optional[float] = None):
        # Is pygame still happy?
        isInit = self.isInit
        self.state.update("initialised", isInit)
        if isInit:
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

    # Sends the current playback position to clients, so they can update their UI frequently.
    # Run on every main loop, but rate limited.
    def _ping_times(self):

        UPDATES_FREQ_SECS = 0.2
        if (
            self.last_time_update is None
            or self.last_time_update + UPDATES_FREQ_SECS < time.time()
        ):
            self.last_time_update = time.time()
            self._retAll("POS:" + str(self.state.get()["pos_true"]))

    # Broadcast a message to all other modules of the BAPSicle server.
    def _retAll(self, msg):
        if self.out_q:
            self.out_q.put("{}:ALL:{}".format(self.state.get()["channel"], msg))

    # Send a response back to an incoming command, with the original content and a success or failure.
    def _retMsg(
        self, msg: Any, okay_str: bool = False, custom_prefix: Optional[str] = None
    ):
        response = "{}:".format(self.state.get()["channel"])
        # Make sure to add the message source back, so that it can be sent to the correct destination in the main server.
        if custom_prefix:
            response += custom_prefix
        else:
            response += "{}:{}:".format(self.last_msg_source, self.last_msg)
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
            if "STATUS:" not in response:
                # Don't fill logs with status pushes, it's a mess.
                self.logger.log.debug(("Sending: {}".format(response)))
            self.out_q.put(response)
        else:
            self.logger.log.exception(
                "Message return Queue is missing!!!! Can't send message."
            )

    # Send the current status to all other modules/clients. Used for updating all client UIs when one of them causes a change etc.
    def _send_status(self):
        self._retMsg(str(self.status), okay_str=True,
                     custom_prefix="ALL:STATUS:")

    # Takes an input show plan, checks and corrects duplicate / gaps in weights, and stores it.
    def _fix_and_update_weights(self, plan: List[PlanItem]):
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

    # Player start up. This is called from the BAPSicle server.py.
    def __init__(
        self,
        channel: int,
        in_q: multiprocessing.Queue,
        out_q: multiprocessing.Queue,
        server_state: StateManager,
    ):

        process_title = "BAPSicle - Player: Channel " + str(channel)
        setproctitle.setproctitle(process_title)
        multiprocessing.current_process().name = process_title

        self.running = True
        self.out_q = out_q

        self.logger = LoggingManager(
            "Player" + str(channel), debug=package.BETA)

        self.api = MyRadioAPI(self.logger, server_state)

        self.state = StateManager(
            "Player" + str(channel),
            self.logger,
            self.__default_state,
            self.__rate_limited_params,
        )

        self.state.update("start_time", datetime.now().timestamp())

        # When the state changes, use _send_status() to tell all clients.
        self.state.add_callback(self._send_status)

        self.state.update("channel", channel)
        # tracklist mode is shared between all players, so grab that from the server config.
        self.state.update("tracklist_mode", server_state.get()[
                          "tracklist_mode"])
        self.state.update(
            "live", True
        )  # Channel Fader is live until controller says it isn't.

        # Just in case there's any weights somehow messed up, let's fix them.
        plan_copy: List[PlanItem] = copy.copy(self.state.get()["show_plan"])
        self._fix_and_update_weights(plan_copy)

        loaded_state = self.state.state

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
            # self.load(loaded_item.weight)

            # Load may jump to the cue point, as it would do on a regular load.
            # If we were at a different state before, we have to override it now.
            if loaded_state["pos_true"] != 0:
                self.logger.log.info(
                    "Seeking to pos_true: " + str(loaded_state["pos_true"])
                )
                try:
                    self.seek(loaded_state["pos_true"])
                except error:
                    self.logger.log.error("Failed to seek on player start. Continuing anyway.")

            if loaded_state["playing"] is True:
                self.logger.log.info("Resuming playback on init.")
                # Use un-pause as we don't want to jump to a new position.
                try:
                    self.unpause()
                except error:
                    self.logger.log.error("Failed to unpause on player start. Continuing anyway.")
        else:
            self.logger.log.info("No file was previously loaded to resume.")

        # The main loop. This keeps running till something tells it to stop.
        try:
            while self.running:
                # Update the state for playback position changes etc
                self._updateState()
                # If we need to, tell clients of the position updates
                self._ping_times()
                try:
                    # Try and get a new command message from clients
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

                    # If we're getting no messages, sleep.
                    # But if we do have messages, once we've done with one, we'll check for the next one more quickly.
                    time.sleep(0.05)
                else:

                    # We got a message.

                    # Check if we're successfully loaded
                    # This is here so that we can check often, but not every single loop
                    # Only when user gives input.
                    self._checkIsLoaded()

                    # Output re-inits the mixer, so we can do this any time.
                    if self.last_msg.startswith("OUTPUT"):
                        split = self.last_msg.split(":")
                        self._retMsg(self.set_output(split[1]))

                    # Only process these commands if we're properly initialised.
                    elif self.isInit:
                        message_types: Dict[
                            str, Callable[..., Any]
                        ] = {  # TODO Check Types
                            "STATUS": lambda: self._retMsg(self.status, True),
                            # Audio Playout
                            # Unpause, so we don't jump to 0, we play from the current pos.
                            "PLAY": lambda: self._retMsg(self.unpause()),
                            "PAUSE": lambda: self._retMsg(self.pause()),
                            "PLAYPAUSE": lambda: self._retMsg(
                                self.unpause() if not self.isPlaying else self.pause()
                            ),  # For the hardware controller.
                            "UNPAUSE": lambda: self._retMsg(self.unpause()),
                            "STOP": lambda: self._retMsg(
                                self.stop(user_initiated=True)
                            ),
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
                            "GETPLAN": lambda: self._retMsg(
                                self.get_plan(int(self.last_msg.split(":")[1]))
                            ),
                            "LOAD": lambda: self._retMsg(
                                self.load(int(self.last_msg.split(":")[1]))
                            ),
                            "LOADED?": lambda: self._retMsg(self.isLoaded),
                            "UNLOAD": lambda: self._retMsg(self.unload()),
                            "ADD": lambda: self._retMsg(
                                self.add_to_plan([
                                    json.loads(
                                        ":".join(self.last_msg.split(":")[1:]))
                                ])
                            ),
                            "REMOVE": lambda: self._retMsg(
                                self.remove_from_plan(
                                    int(self.last_msg.split(":")[1]))
                            ),
                            "CLEAR": lambda: self._retMsg(self.clear_channel_plan()),
                            "SETMARKER": lambda: self._retMsg(
                                self.set_marker(
                                    self.last_msg.split(":")[1],
                                    self.last_msg.split(":", 2)[2],
                                )
                            ),
                            "RESETPLAYED": lambda: self._retMsg(
                                self.set_played(
                                    weight=int(self.last_msg.split(":")[1]),
                                    played=False,
                                )
                            ),
                            "SETPLAYED": lambda: self._retMsg(
                                self.set_played(
                                    weight=int(self.last_msg.split(":")[1]), played=True
                                )
                            ),
                            "SETLIVE": lambda: self._retMsg(
                                self.set_live(
                                    self.last_msg.split(":")[1] == "True")
                            ),
                        }

                        message_type: str = self.last_msg.split(":")[0]

                        # From the list above, work out which command type we have, and run it's handling function.
                        if message_type in message_types.keys():
                            message_types[message_type]()

                        elif self.last_msg == "QUIT":
                            self._retMsg(True)
                            self.running = False
                            continue

                        else:
                            self._retMsg("Unknown Command")
                    else:
                        # We're not initialised, return a failed status if they asked for one, or just say the command failed
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
