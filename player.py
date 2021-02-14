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

from helpers.types import PlayerState, RepeatMode
from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time
import sys

from typing import Any, Callable, Dict, List, Optional

from plan import PlanItem

# Stop the Pygame Hello message.
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
from pygame import mixer, NOEVENT, USEREVENT, event, init
from mutagen.mp3 import MP3

from helpers.myradio_api import MyRadioAPI
from helpers.os_environment import isMacOS
from helpers.state_manager import StateManager
from helpers.logging_manager import LoggingManager

PLAYBACK_END = USEREVENT + 1
class Player():
    state = None
    running = False
    out_q = None
    last_msg = ""
    last_time_update = None
    logger = None
    api = None
    already_stopped = False
    starting = False

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
        "repeat": "NONE",  # NONE, ONE or ALL
        "play_on_load": False,
        "output": None,
        "show_plan": []
    }

    __rate_limited_params = [
        "pos",
        "pos_offset",
        "pos_true",
        "remaining"
    ]

    @property
    def isInit(self):
        try:
            mixer.music.get_busy()
        except:
            return False

        return True

    @property
    def isPlaying(self):
        if self.isInit:
            return (not self.isPaused) and bool(mixer.music.get_busy())
        return False

    @property
    def isPaused(self) -> bool:
        return self.state.state["paused"]

    @property
    def isLoaded(self):
        if not self.state.state["loaded_item"]:
            return False
        if self.isPlaying:
            return True

        # Because Pygame/SDL is annoying
        # We're not playing now, so we can quickly test run
        # If that works, we're loaded.
        try:
            position: float = self.state.state["pos"]
            mixer.music.set_volume(0)
            mixer.music.play(0)
        except:
            try:
                mixer.music.set_volume(1)
            except:
                self.logger.log.exception("Failed to reset volume after attempting loaded test.")
                pass
            return False
        if position > 0:
            self.pause()
        else:
            self.stop()
        mixer.music.set_volume(1)
        return True

    @property
    def status(self):
        state = copy.copy(self.state.state)

        # Not the biggest fan of this, but maybe I'll get a better solution for this later
        state["loaded_item"] = state["loaded_item"].__dict__ if state["loaded_item"] else None
        state["show_plan"] = [repr.__dict__ for repr in state["show_plan"]]

        res = json.dumps(state)
        return res

    # Audio Playout Related Methods

    def play(self, pos: float = 0):
        global starting
        global already_stopped
        starting = True
        try:
            mixer.music.play(0, pos)
            mixer.music.set_endevent(PLAYBACK_END)
            self.state.update("pos_offset", pos)
        except:
            self.logger.log.exception("Failed to play at pos: " + str(pos))
            return False
        self.state.update("paused", False)

        already_stopped = False
        return True

    def pause(self):
        try:
            mixer.music.pause()
        except:
            self.logger.log.exception("Failed to pause.")
            return False
        self.state.update("paused", True)
        return True

    def unpause(self):
        if not self.isPlaying:
            position: float = self.state.state["pos_true"]
            try:
                self.play(position)
            except:
                self.logger.log.exception("Failed to unpause from pos: " + str(position))
                return False
            self.state.update("paused", False)
            return True
        return False

    def stop(self):
        # if self.isPlaying or self.isPaused:
        try:
            mixer.music.stop()
        except:
            self.logger.log.exception("Failed to stop playing.")
            return False
        self.state.update("pos", 0)
        self.state.update("pos_offset", 0)
        self.state.update("pos_true", 0)
        self.state.update("paused", False)

        global already_stopped
        already_stopped = True

        return True
        # return False

    def seek(self, pos: float) -> bool:
        if self.isPlaying:
            try:
                self.play(pos)
            except:
                self.logger.log.exception("Failed to seek to pos: " + str(pos))
                return False
            return True
        else:
            self.state.update("paused", True)
            self._updateState(pos=pos)
        return True

    def set_auto_advance(self, message: int) -> bool:
        if message == 0:
            self.state.update("auto_advance", False)
            return True  # It did it
        elif message == 1:
            self.state.update("auto_advance", True)
            return True
        else:
            return False

    def set_repeat(self, message: str) -> bool:
        if message in ["ALL", "ONE", "NONE"]:
            self.state.update("repeat", message)
            return True
        else:
            return False

    def set_play_on_load(self, message: int) -> bool:
        if message == 0:
            self.state.update("play_on_load", False)
            return True  # It did it
        elif message == 1:
            self.state.update("play_on_load", True)
            return True
        else:
            return False

    # Show Plan Related Methods
    def get_plan(self, message: int):
        plan = self.api.get_showplan(message)
        self.clear_channel_plan()
        channel = self.state.state["channel"]
        if len(plan) > channel:
            for plan_item in plan[str(channel)]:
                try:
                    new_item: Dict[str, any] = {
                        "channelWeight": int(plan_item["weight"]),
                        "filename": None,
                        "title":  plan_item["title"],
                        "artist":  plan_item["artist"] if "artist" in plan_item.keys() else None,
                        "timeslotItemId": int(plan_item["timeslotitemid"]) if "timeslotitemid" in plan_item.keys() and plan_item["timeslotitemid"] != None else None,
                        "trackId": int(plan_item["trackid"]) if "managedid" not in plan_item.keys() and plan_item["trackid"] != None else None,
                        "recordId": int(plan_item["trackid"]) if "trackid" in plan_item.keys() and plan_item["trackid"] != None else None, # TODO This is wrong.
                        "managedId": int(plan_item["managedid"]) if "managedid" in plan_item.keys() and plan_item["managedid"] != None else None,
                    }
                    self.add_to_plan(new_item)
                except:
                    continue

        return True


    def add_to_plan(self, new_item: Dict[str, Any]) -> bool:
        self.state.update("show_plan", self.state.state["show_plan"] + [PlanItem(new_item)])
        return True

    def remove_from_plan(self, channel_weight: int) -> bool:
        plan_copy: List[PlanItem] = copy.copy(self.state.state["show_plan"])
        for i in plan_copy:
            if i.channelWeight == channel_weight:
                plan_copy.remove(i)
                self.state.update("show_plan", plan_copy)
                return True
        return False

    def clear_channel_plan(self) -> bool:
        self.state.update("show_plan", [])
        return True

    def load(self, channelWeight: int):
        if not self.isPlaying:
            self.unload()

            showplan = self.state.state["show_plan"]

            loaded_item: Optional[PlanItem] = None

            for i in range(len(showplan)):
                if showplan[i].channelWeight == channelWeight:
                    loaded_item = showplan[i]
                    break

            if loaded_item == None:
                self.logger.log.error("Failed to find channelWeight: {}".format(channelWeight))
                return False

            if (loaded_item.filename == "" or loaded_item.filename == None):
                loaded_item.filename = self.api.get_filename(item = loaded_item)

            if not loaded_item.filename:
                return False

            self.state.update("loaded_item", loaded_item)

            for i in range(len(showplan)):
                if showplan[i].channelWeight == channelWeight:
                    self.state.update("show_plan", index=i, value=loaded_item)
                break
                # TODO: Update the show plan filenames

            try:
                self.logger.log.info("Loading file: " + str(loaded_item.filename))
                mixer.music.load(loaded_item.filename)
            except:
                # We couldn't load that file.
                self.logger.log.exception("Couldn't load file: " + str(loaded_item.filename))
                return False

            try:
                if ".mp3" in loaded_item.filename:
                    song = MP3(loaded_item.filename)
                    self.state.update("length", song.info.length)
                else:
                    self.state.update("length", mixer.Sound(loaded_item.filename).get_length()/1000)
            except:
                self.logger.log.exception("Failed to update the length of item.")
                return False

            if self.state.state["play_on_load"]:
                self.play()

        return True

    def unload(self):
        if not self.isPlaying:
            try:
                mixer.music.unload()
                self.state.update("paused", False)
                self.state.update("loaded_item", None)
            except:
                self.logger.log.exception("Failed to unload channel.")
                return False
        return not self.isLoaded

    def quit(self):
        try:
            mixer.quit()
            self.state.update("paused", False)
        except:
            self.logger.log.exception("Failed to quit mixer.")

    def output(self, name: Optional[str] = None):
        wasPlaying = self.state.state["playing"]
        name = None if name == "none" else name

        self.quit()
        self.state.update("output", name)
        try:
            if name:
                mixer.init(44100, -16, 2, 1024, devicename=name)
            else:
                mixer.init(44100, -16, 2, 1024)
        except:
            self.logger.log.exception("Failed to init mixer with device name: " + str(name))
            return False

        loadedItem = self.state.state["loaded_item"]
        if (loadedItem):
            self.load(loadedItem.channelWeight)
        if wasPlaying:
            self.unpause()

        return True

    def ended(self):
        loaded_item = self.state.state["loaded_item"]
        # check the existing state (not self.isPlaying)
        # Since this is called multiple times when pygame isn't playing.

        global starting

        if starting:
            print("Starting")
            starting = False
            return



        global already_stopped

        print(already_stopped, self.state.state["remaining"], self.isPlaying)

        if loaded_item == None or already_stopped or (self.state.state["remaining"] > 1):
            return

        mixer.music.set_endevent(NOEVENT)

        already_stopped = True


        stopping = True

        # Track has ended
        print("Finished", loaded_item.name)

        # Repeat 1
        if self.state.state["repeat"] == "ONE":
            self.play()
            stopping = False

        # Auto Advance
        elif self.state.state["auto_advance"]:
            for i in range(len(self.state.state["show_plan"])):
                if self.state.state["show_plan"][i].channelWeight == loaded_item.channelWeight:
                    if len(self.state.state["show_plan"]) > i+1:
                        self.load(self.state.state["show_plan"][i+1].channelWeight)
                        break

                    # Repeat All
                    elif self.state.state["repeat"] == "ALL":
                        self.load(self.state.state["show_plan"][0].channelWeight)

        # Play on Load
        if self.state.state["play_on_load"]:
            self.play()
            stopping = False

        if stopping:
            self.stop()
            if self.out_q:
                self.out_q.put("STOPPED") # Tell clients that we've stopped playing.

    def _updateState(self, pos: Optional[float] = None):

        self.state.update("initialised", self.isInit)
        if self.isInit:
            if (pos):
                self.state.update("pos", max(0, pos))
            elif self.isPlaying:
                # Get one last update in, incase we're about to pause/stop it.
                self.state.update("pos", max(0, mixer.music.get_pos()/1000))
            self.state.update("playing", self.isPlaying)
            self.state.update("loaded", self.isLoaded)

            self.state.update("pos_true", self.state.state["pos"] + self.state.state["pos_offset"])

            self.state.update("remaining", self.state.state["length"] - self.state.state["pos_true"])

    def _ping_times(self):
        if self.last_time_update == None or self.last_time_update + 1 < time.time():
            self.last_time_update = time.time()
            self.out_q.put("POS:" + str(int(self.state.state["pos_true"])))



    def _retMsg(self, msg: Any, okay_str: Any = False):
        response = self.last_msg + ":"
        if msg == True:
            response += "OKAY"
        elif isinstance(msg, str):
            if okay_str:
                response += "OKAY:" + msg
            else:
                response += "FAIL:" + msg
        else:
            response += "FAIL"
        self.logger.log.info(("Preparing to send: {}".format(response)))
        if self.out_q:
            self.logger.log.info(("Sending: {}".format(response)))
            self.out_q.put(response)

    def __init__(self, channel: int, in_q: multiprocessing.Queue, out_q: multiprocessing.Queue):

        process_title = "Player: Channel " + str(channel)
        setproctitle.setproctitle(process_title)
        multiprocessing.current_process().name = process_title

        # Init pygame, only used really for the end of playback trigger.
        init()

        self.running = True
        self.out_q = out_q

        self.logger = LoggingManager("channel" + str(channel))

        self.api = MyRadioAPI(self.logger)

        self.state = StateManager("channel" + str(channel), self.logger,
                                  self.__default_state, self.__rate_limited_params)
        self.state.update("channel", channel)

        loaded_state = copy.copy(self.state.state)

        if loaded_state["output"]:
            self.logger.log.info("Setting output to: " + str(loaded_state["output"]))
            self.output(loaded_state["output"])
        else:
            self.logger.log.info("Using default output device.")
            self.output()

        loaded_item = loaded_state["loaded_item"]
        if loaded_item:
            self.logger.log.info("Loading filename: " + str(loaded_item.filename))
            self.load(loaded_item.channelWeight)

            if loaded_state["pos_true"] != 0:
                self.logger.log.info("Seeking to pos_true: " + str(loaded_state["pos_true"]))
                self.seek(loaded_state["pos_true"])

            if loaded_state["playing"] == True:
                self.logger.log.info("Resuming.")
                self.unpause()
        else:
            self.logger.log.info("No file was previously loaded.")

        while self.running:
            time.sleep(0.1)
            self._updateState()
            self._ping_times()
            try:
                try:
                    self.last_msg = in_q.get_nowait()
                except Empty:
                    # The incomming message queue was empty,
                    # skip message processing
                    pass
                else:

                    # We got a message.

                    # Output re-inits the mixer, so we can do this any time.
                    if (self.last_msg.startswith("OUTPUT")):
                        split = self.last_msg.split(":")
                        self._retMsg(self.output(split[1]))

                    elif self.isInit:

                        message_types: Dict[str, Callable[..., Any]] = { # TODO Check Types
                            "STATUS": lambda: self._retMsg(self.status, True),

                            # Audio Playout
                            "PLAY": lambda: self._retMsg(self.play()),
                            "PAUSE": lambda: self._retMsg(self.pause()),
                            "UNPAUSE": lambda: self._retMsg(self.unpause()),
                            "STOP": lambda: self._retMsg(self.stop()),
                            "SEEK": lambda: self._retMsg(self.seek(float(self.last_msg.split(":")[1]))),
                            "AUTOADVANCE": lambda: self._retMsg(self.set_auto_advance(int(self.last_msg.split(":")[1]))),
                            "REPEAT": lambda: self._retMsg(self.set_repeat(self.last_msg.split(":")[1])),
                            "PLAYONLOAD": lambda: self._retMsg(self.set_play_on_load(int(self.last_msg.split(":")[1]))),

                            # Show Plan Items
                            "GET_PLAN": lambda: self._retMsg(self.get_plan(int(self.last_msg.split(":")[1]))),

                            "LOAD": lambda: self._retMsg(self.load(int(self.last_msg.split(":")[1]))),
                            "LOADED?": lambda: self._retMsg(self.isLoaded),
                            "UNLOAD": lambda: self._retMsg(self.unload()),
                            "ADD": lambda: self._retMsg(self.add_to_plan(json.loads(":".join(self.last_msg.split(":")[1:])))),
                            "REMOVE": lambda: self._retMsg(self.remove_from_plan(int(self.last_msg.split(":")[1]))),
                            "CLEAR": lambda: self._retMsg(self.clear_channel_plan())
                        }

                        message_type: str = self.last_msg.split(":")[0]

                        if message_type in message_types.keys():
                            message_types[message_type]()

                            if message_type != "STATUS":
                                ## Then a super hacky hack. Send the status again to update Webstudio
                                self._updateState()
                                self.last_msg = "STATUS"
                                self._retMsg(self.status, True)

                        elif (self.last_msg == 'QUIT'):
                            self.running = False
                            continue

                        else:
                            self._retMsg("Unknown Command")
                    else:

                        if (self.last_msg == 'STATUS'):
                            self._retMsg(self.status)
                        else:
                            self._retMsg(False)



                try:
                    callback_event = event.poll()
                    if callback_event.type == PLAYBACK_END:
                        self.ended()
                    else:
                        pass
                except Exception as e:
                    pass



            # Catch the player being killed externally.
            except KeyboardInterrupt:
                self.logger.log.info("Received KeyboardInterupt")
                break
            except SystemExit:
                self.logger.log.info("Received SystemExit")
                break
            except Exception as e:
                self.logger.log.exception("Received unexpected exception: {}".format(e))
                break

        self.logger.log.info("Quiting player ", channel)
        self.quit()
        self._retMsg("EXIT")
        sys.exit(0)


def showOutput(in_q: multiprocessing.Queue, out_q: multiprocessing.Queue):
    print("Starting showOutput().")
    while True:
        time.sleep(0.01)
        last_msg = out_q.get()
        print(last_msg)


if __name__ == "__main__":
    if isMacOS():
        multiprocessing.set_start_method("spawn", True)

    in_q: multiprocessing.Queue[Any] = multiprocessing.Queue()
    out_q: multiprocessing.Queue[Any] = multiprocessing.Queue()

    outputProcess = multiprocessing.Process(
        target=showOutput,
        args=(in_q, out_q),
    ).start()

    playerProcess = multiprocessing.Process(
        target=Player,
        args=(-1, in_q, out_q),
    ).start()

    # Do some testing
    in_q.put("LOADED?")
    in_q.put("PLAY")
    in_q.put("LOAD:dev/test.mp3")
    in_q.put("LOADED?")
    in_q.put("PLAY")
    print("Entering infinite loop.")
    while True:
        pass
