from state_manager import StateManager
from mutagen.mp3 import MP3
from pygame import mixer
import time
import json
import copy
import os
import setproctitle

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"


class Player():
    state = None
    running = False

    __default_state = {
        "filename": "",
        "channel": -1,
        "playing": False,
        "pos": 0,
        "remaining": 0,
        "length": 0,
        "loop": False,
        "output": None
    }

    def isInit(self):
        try:
            mixer.music.get_busy()
        except:
            return False
        else:
            return True

    def isPlaying(self):
        return bool(mixer.music.get_busy())

    def play(self):

        mixer.music.play(0)

    def pause(self):
        mixer.music.pause()

    def unpause(self):
        mixer.music.play(0, self.state.state["pos"])

    def stop(self):
        mixer.music.stop()

    def seek(self, pos):
        if self.isPlaying():
            mixer.music.play(0, pos)
        else:
            self.updateState(pos)

    def load(self, filename):
        if not self.isPlaying():
            self.state.update("filename", filename)
            mixer.music.load(filename)
            if ".mp3" in filename:
                song = MP3(filename)
                self.state.update("length", song.info.length)
            else:
                self.state.update("length", mixer.Sound(filename).get_length()/1000)

    def quit(self):
        mixer.quit()

    def output(self, name=None):
        self.quit()
        try:
            if name:
                mixer.init(44100, -16, 1, 1024, devicename=name)
            else:
                mixer.init(44100, -16, 1, 1024)
        except:
            return "FAIL:Failed to init mixer, check sound devices."
        else:
            self.state.update("output", name)

        return "OK"

    def updateState(self, pos=None):
        self.state.update("playing", self.isPlaying())
        if (pos):
            self.state.update("pos", max(0, pos))
        else:
            self.state.update("pos", max(0, mixer.music.get_pos()/1000))
        self.state.update("remaining", self.state.state["length"] - self.state.state["pos"])

    def getDetails(self):
        res = "RESP:DETAILS: " + json.dumps(self.state.state)
        return res

    def __init__(self, channel, in_q, out_q):
        self.running = True
        setproctitle.setproctitle("BAPSicle - Player " + str(channel))

        self.state = StateManager("channel" + str(channel), self.__default_state)

        self.state.update("channel", channel)

        loaded_state = copy.copy(self.state.state)

        if loaded_state["output"]:
            print("Setting output to: " + loaded_state["output"])
            self.output(loaded_state["output"])
        else:
            self.output()

        if loaded_state["filename"]:
            print("Loading filename: " + loaded_state["filename"])
            self.load(loaded_state["filename"])

        if loaded_state["pos"] != 0:
            print("Seeking to pos: " + str(loaded_state["pos"]))
            self.seek(loaded_state["pos"])

        if loaded_state["playing"] == True:
            print("Resuming.")
            self.unpause()

        while self.running:
            time.sleep(0.01)
            incoming_msg = in_q.get()
            if (not incoming_msg):
                continue
            if self.isInit():
                self.updateState()
                if (incoming_msg == 'PLAY'):
                    self.play()
                if (incoming_msg == 'PAUSE'):
                    self.pause()
                if (incoming_msg == 'UNPAUSE'):
                    self.unpause()
                if (incoming_msg == 'STOP'):
                    self.stop()
                if (incoming_msg == 'QUIT'):
                    self.quit()
                    self.running = False
                if (incoming_msg.startswith("SEEK")):
                    split = incoming_msg.split(":")
                    self.seek(float(split[1]))
                if (incoming_msg.startswith("LOAD")):
                    split = incoming_msg.split(":")
                    self.load(split[1])
                if (incoming_msg == 'DETAILS'):
                    out_q.put(self.getDetails())

            if (incoming_msg.startswith("OUTPUT")):
                split = incoming_msg.split(":")
                out_q.put(self.output(split[1]))

        print("Quiting player ", channel)
