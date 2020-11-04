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

from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time

from typing import Callable, Dict, List

from plan import PlanObject

import os
import sys

from pygame import mixer
from mutagen.mp3 import MP3

from state_manager import StateManager
from helpers.os_environment import isMacOS

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

class Player():
    state = None
    running = False
    out_q = None
    last_msg = None

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
        "repeat": "NONE", #NONE, ONE or ALL
        "play_on_load": False,
        "output": None,
        "show_plan": []
    }

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
    def isPaused(self):
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
            position = self.state.state["pos"]
            mixer.music.set_volume(0)
            mixer.music.play(0)
        except:
            try:
                mixer.music.set_volume(1)
            except:
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

    ### Audio Playout Related Methods

    def play(self, pos=0):
        # if not self.isPlaying:
        try:
            mixer.music.play(0, pos)
            self.state.update("pos_offset", pos)
        except:
            return False
        self.state.update("paused", False)
        return True
        # return False

    def pause(self):
        # if self.isPlaying:

        try:
            mixer.music.pause()
        except:
            return False
        self.state.update("paused", True)
        return True
        # return False

    def unpause(self):
        if not self.isPlaying:
            try:
                self.play(self.state.state["pos_true"])
            except:
                return False
            self.state.update("paused", False)
            return True
        return False

    def stop(self):
        # if self.isPlaying or self.isPaused:
        try:
            mixer.music.stop()
        except Exception as e:
            print("Couldn't Stop Player:", e)
            return False
        self.state.update("pos", 0)
        self.state.update("pos_offset", 0)
        self.state.update("pos_true", 0)
        self.state.update("paused", False)
        return True
        # return False

    def seek(self, pos):
        if self.isPlaying:
            try:
                self.play(pos)
            except:
                return False
            return True
        else:
            self.state.update("paused", True)
            self._updateState(pos=pos)
        return True

    def set_auto_advance(self, message: int) -> bool:
        if message == 0:
            self.state.update("auto_advance", False)
            return True # It did it
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
            return True # It did it
        elif message == 1:
            self.state.update("play_on_load", True)
            return True
        else:
            return False

    ### Show Plan Related Methods

    def add_to_plan(self, new_item: Dict[str, any]) -> bool:
        self.state.update("show_plan", self.state.state["show_plan"] + [PlanObject(new_item)])
        return True

    def remove_from_plan(self, timeslotitemid: int) -> bool:
        plan_copy = copy.copy(self.state.state["show_plan"])
        for i in range(len(plan_copy)):
            if plan_copy[i].timeslotitemid == timeslotitemid:
                plan_copy.remove(i)
                self.state.update("show_plan", plan_copy)
                return True
        return False

    def clear_channel_plan(self) -> bool:
        self.state.update("show_plan", [])
        return True

    def load(self, timeslotitemid: int):
        if not self.isPlaying:
            self.unload()

            updated: bool = False
            
            for i in range(len(self.state.state["show_plan"])):
                if self.state.state["show_plan"][i].timeslotitemid == timeslotitemid:
                    self.state.update("loaded_item", self.state.state["show_plan"][i])
                    updated = True
                    break

            if not updated:
                print("Failed to find timeslotitemid:", timeslotitemid)
                return False

            filename: str = self.state.state["loaded_item"].filename


            try:
                mixer.music.load(filename)
            except:
                # We couldn't load that file.
                print("Couldn't load file:", filename)
                return False

            try:
                if ".mp3" in filename:
                    song = MP3(filename)
                    self.state.update("length", song.info.length)
                else:
                    self.state.update("length", mixer.Sound(filename).get_length()/1000)
            except:
                return False
        return True

    def unload(self):
        if not self.isPlaying:
            try:
                mixer.music.unload()
                self.state.update("paused", False)
                self.state.update("loaded_item", None)
            except:
                return False
        return not self.isLoaded

    def quit(self):
        mixer.quit()
        self.state.update("paused", False)

    def output(self, name=None):
        self.quit()
        self.state.update("output", name)
        self.state.update("loaded_item", None)
        try:
            if name:
                mixer.init(44100, -16, 1, 1024, devicename=name)
            else:
                mixer.init(44100, -16, 1, 1024)
        except:
            return False

        return True

    def _updateState(self, pos=None):
        self.state.update("initialised", self.isInit)
        if self.isInit:
            # TODO: get_pos returns the time since the player started playing
            # This is NOT the same as the position through the song.
            if self.isPlaying:
                # Get one last update in, incase we're about to pause/stop it.
                self.state.update("pos", max(0, mixer.music.get_pos()/1000))
            self.state.update("playing", self.isPlaying)
            self.state.update("loaded", self.isLoaded)

            if (pos):
                self.state.update("pos", max(0, pos))

            self.state.update("pos_true", self.state.state["pos"] + self.state.state["pos_offset"])

            self.state.update("remaining", self.state.state["length"] - self.state.state["pos_true"])

            if self.state.state["remaining"] == 0 and self.state.state["loaded_item"]:
                # Track has ended
                print("Finished", self.state.state["loaded_item"].name)
                
                # Repeat 1
                if self.state.state["repeat"] == "ONE":
                    self.play()

                # Auto Advance
                elif self.state.state["auto_advance"]:
                    for i in range(len(self.state.state["show_plan"])):
                        if self.state.state["show_plan"][i].timeslotitemid == self.state.state["loaded_item"].timeslotitemid:
                            if len(self.state.state["show_plan"]) > i+1:
                                self.load(self.state.state["show_plan"][i+1].timeslotitemid)
                                break

                            # Repeat All
                            elif self.state.state["repeat"] == "ALL":
                                self.load(self.state.state["show_plan"][0].timeslotitemid)
                
                # Play on Load
                if self.state.state["play_on_load"]:
                    self.play()
                

    def _retMsg(self, msg, okay_str=False):
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
        if self.out_q:
            self.out_q.put(response)

    def __init__(self, channel, in_q, out_q):
        self.running = True
        self.out_q = out_q

        setproctitle.setproctitle("BAPSicle - Player " + str(channel))

        self.state = StateManager("channel" + str(channel), self.__default_state)

        self.state.update("channel", channel)

        loaded_state = copy.copy(self.state.state)

        if loaded_state["output"]:
            print("Setting output to: " + loaded_state["output"])
            self.output(loaded_state["output"])
        else:
            print("Using default output device.")
            self.output()

        if loaded_state["loaded_item"]:
            print("Loading filename: " + loaded_state["loaded_item"].filename)
            self.load(loaded_state["loaded_item"].timeslotitemid)

            if loaded_state["pos_true"] != 0:
                print("Seeking to pos_true: " + str(loaded_state["pos_true"]))
                self.seek(loaded_state["pos_true"])

            if loaded_state["playing"] == True:
                print("Resuming.")
                self.unpause()
        else:
            print("No file was previously loaded.")

        while self.running:
            time.sleep(0.1)
            self._updateState()
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

                        message_types: Dict[str, Callable[any, bool]] = { # TODO Check Types
                            "STATUS":       lambda: self._retMsg(self.status, True),
                            
                            # Audio Playout
                            "PLAY":         lambda: self._retMsg(self.play()),
                            "PAUSE":        lambda: self._retMsg(self.pause()),
                            "UNPAUSE":      lambda: self._retMsg(self.unpause()),
                            "STOP":         lambda: self._retMsg(self.stop()),
                            "SEEK":         lambda: self._retMsg(self.seek(float(self.last_msg.split(":")[1]))),
                            "AUTOADVANCE":  lambda: self._retMsg(self.set_auto_advance(int(self.last_msg.split(":")[1]))),
                            "REPEAT":       lambda: self._retMsg(self.set_repeat(self.last_msg.split(":")[1])),
                            "PLAYONLOAD":   lambda: self._retMsg(self.set_play_on_load(int(self.last_msg.split(":")[1]))),

                            # Show Plan Items
                            "LOAD":         lambda: self._retMsg(self.load(int(self.last_msg.split(":")[1]))),
                            "LOADED?":      lambda: self._retMsg(self.isLoaded),
                            "UNLOAD":       lambda: self._retMsg(self.unload()),
                            "ADD":          lambda: self._retMsg(self.add_to_plan(json.loads(":".join(self.last_msg.split(":")[1:])))),
                            "REMOVE":       lambda: self._retMsg(self.remove_from_plan(int(self.last_msg.split(":")[1]))),
                            "CLEAR":        lambda: self._retMsg(self.clear_channel_plan())
                        }

                        message_type: str = self.last_msg.split(":")[0]

                        if message_type in message_types.keys():
                            message_types[message_type]()

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

            # Catch the player being killed externally.
            except KeyboardInterrupt:
                break
            except SystemExit:
                break
            except:
                raise

        print("Quiting player ", channel)
        self.quit()
        self._retMsg("EXIT")
        sys.exit(0)


def showOutput(in_q, out_q):
    print("Starting showOutput().")
    while True:
        time.sleep(0.01)
        last_msg = out_q.get()
        print(last_msg)


if __name__ == "__main__":
    if isMacOS:
        multiprocessing.set_start_method("spawn", True)

    in_q = multiprocessing.Queue()
    out_q = multiprocessing.Queue()

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
