import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
os.putenv('SDL_AUDIODRIVER', 'pulseaudio')
import pygame._sdl2 as sdl2
import pygame
from pygame import mixer
pygame.init()
import time
mixer.init(44100, -16, 2, 1024)
is_capture = 0  # zero to request playback devices, non-zero to request recording devices
num = sdl2.get_num_audio_devices(is_capture)
names = [str(sdl2.get_audio_device_name(i, is_capture), encoding="utf-8") for i in range(num)]
mixer.quit()
for i in names:
    print(i)
    mixer.init(44100, -16, 2, 1024, devicename=i)
    print(mixer.get_init())
    mixer.music.load("/home/mstratford/Downloads/managed_play.mp3")
    mixer.music.play()
    # my_song = mixer.Sound("/home/mstratford/Downloads/managed_play.mp3")
    # my_song.play()
    time.sleep(5)
    pygame.quit()
