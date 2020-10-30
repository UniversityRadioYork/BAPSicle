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
    out_q = None
    last_msg = None

    __default_state = {
        "initialised": False,
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
            mixer.music.pause()
        else:
            mixer.music.stop()
        mixer.music.set_volume(1)
        return True

    @property
    def status(self):
        res = json.dumps(self.state.state)
        return res

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
        self.state.update("output", name)
        self.state.update("filename", "")
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
            self.state.update("playing", self.isPlaying)
            self.state.update("loaded", self.isLoaded)
            if (pos):
                self.state.update("pos", max(0, pos))
            else:
                self.state.update("pos", max(0, mixer.music.get_pos()/1000))
            self.state.update("remaining", self.state.state["length"] - self.state.state["pos"])

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

                        if (self.last_msg == 'LOADED?'):
                            self._retMsg(self.isLoaded)
                            continue

                        elif (self.last_msg == 'PLAY'):
                            self._retMsg(self.play())

                        elif (self.last_msg == 'PAUSE'):
                            self._retMsg(self.pause())

                        elif (self.last_msg == 'UNPAUSE'):
                            self._retMsg(self.unpause())

                        elif (self.last_msg == 'STOP'):
                            self._retMsg(self.stop())

                        elif (self.last_msg == 'QUIT'):
                            self.running = False
                            continue

                        elif (self.last_msg.startswith("SEEK")):
                            split = self.last_msg.split(":")
                            self._retMsg(self.seek(float(split[1])))

                        elif (self.last_msg.startswith("LOAD")):
                            split = self.last_msg.split(":")
                            self._retMsg(self.load(split[1]))

                        elif (self.last_msg == 'UNLOAD'):
                            self._retMsg(self.unload())

                        elif (self.last_msg == 'STATUS'):
                            self._retMsg(self.status, True)

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


def showOutput(in_q, out_q):
    print("Starting showOutput().")
    while True:
        time.sleep(0.01)
        self.last_msg = out_q.get()
        print(self.last_msg)


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
