import pygame
import time
import json
from mutagen.mp3 import MP3

class bapsicle():
  state = {
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
      pygame.mixer.music.get_busy()
    except:
      return False
    else:
      return True

  def isPlaying(self):
    return bool(pygame.mixer.music.get_busy())

  def play(self):


    pygame.mixer.music.play(0)

  def pause(self):
    pygame.mixer.music.pause()

  def unpause(self):
    pygame.mixer.music.play(0, self.state["pos"])

  def stop(self):
    pygame.mixer.music.stop()

  def seek(self, pos):
    if self.isPlaying():
      pygame.mixer.music.play(0, pos)
    else:
      self.updateState(pos)

  def load(self, filename):
    if not self.isPlaying():
      self.state["filename"] = filename
      pygame.mixer.music.load(filename)
      if ".mp3" in filename:
        song = MP3(filename)
        self.state["length"] = song.info.length
      else:
        self.state["length"] = pygame.mixer.Sound(filename).get_length()/1000

  def output(self, name = None):
    pygame.mixer.quit()
    try:
      if name:
        pygame.mixer.init(44100, -16, 1, 1024, devicename=name)
      else:
        pygame.mixer.init(44100, -16, 1, 1024)
    except:
      return "FAIL:Failed to init mixer, check sound devices."
    else:
      if name:
        self.state["output"] = name
      else:
        self.state["output"] = "default"
      return "OK"


  def updateState(self, pos = None):
    self.state["playing"] = self.isPlaying()
    if (pos):
      self.state["pos"] = pos
    else:
      self.state["pos"] = pygame.mixer.music.get_pos()/1000

    self.state["remaining"] = self.state["length"] - self.state["pos"]

  def getDetails(self):
    res = "RESP:DETAILS: " + json.dumps(self.state)
    return res


  def __init__(self, channel, in_q, out_q):

    self.state["channel"] = channel

    self.output()




    while True:
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

