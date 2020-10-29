from queue import Empty
import multiprocessing
import setproctitle
import copy
import json
import time
from pygame import mixer
from state_manager import StateManager
from mutagen.mp3 import MP3
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"


class Player():
    state = None
    running = False

    __default_state = {
        "filename": "",
        "channel": -1,
        "playing": False,
        "loaded": False,
        "pos": 0,
        "remaining": 0,
        "length": 0,
        "loop": False,
        "output": None
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
            return bool(mixer.music.get_busy())
        return False

    @property
    def isLoaded(self):
        if not self.state.state["filename"]:
            return False
        if self.isPlaying:
            return True

        try:
            current_pos = mixer.music.get_pos()
            mixer.music.set_pos(current_pos)
        except:
            # TODO: Trigger specially off the SDLError (couldn't find it)
            return False

        return False

    def play(self):
        if not self.isPlaying:
            try:
                mixer.music.play(0)
            except:
                return False

            return True
        return False

    def pause(self):
        if self.isPlaying:
            try:
                mixer.music.pause()
            except:
                return False

            return True
        return False

    def unpause(self):
        if not self.isPlaying:
            try:
                mixer.music.play(0, self.state.state["pos"])
            except:
                return False

            return True
        return False

    def stop(self):
        if self.isPlaying:
            try:
                mixer.music.stop()
            except:
                return False

            return True
        return False

    def seek(self, pos):
        if self.isPlaying:
            try:
                mixer.music.play(0, pos)
            except:
                return False
            return True

        return False

    def load(self, filename):
        if not self.isPlaying:

            self.state.update("filename", filename)

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
                self.state.update("filename", "")
            except:
                return False
        return not self.isLoaded

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
        self.state.update("playing", self.isPlaying)
        self.state.update("loaded", self.isLoaded)
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
            print("Using default output device.")
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
        else:
            print("No file was previously loaded.")

        while self.running:
            time.sleep(0.01)
            try:
                try:
                    incoming_msg = in_q.get_nowait()
                except Empty:
                    # The incomming message queue was empty,
                    # skip message processing
                    pass
                else:
                    # We got a message.
                    if self.isInit:

                        self.updateState()

                        if (incoming_msg == 'LOADED?'):
                            out_q.put(self.isLoaded)
                            continue

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

            # Catch the player being killed externally.
            except KeyboardInterrupt:
                break
            except SystemExit:
                break
            except:
                raise

        print("Quiting player ", channel)
        self.quit()


def showOutput(in_q, out_q):
    print("Starting showOutput().")
    while True:
        time.sleep(0.01)
        incoming_msg = out_q.get()
        print(incoming_msg)


if __name__ == "__main__":

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
    in_q.put("LOAD:\\Users\\matth\\Documents\\GitHub\\bapsicle\\dev\\test.mp3")
    in_q.put("LOADED?")
    in_q.put("PLAY")
    print("Entering infinite loop.")
    while True:
        pass
