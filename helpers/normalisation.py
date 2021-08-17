import os
from helpers.os_environment import resolve_external_file_path
from pydub import AudioSegment, effects # Audio leveling!

# Stuff to help make BAPSicle play out leveled audio.
def match_target_amplitude(sound, target_dBFS):
  change_in_dBFS = target_dBFS - sound.dBFS
  return sound.apply_gain(change_in_dBFS)

# Takes
def generate_normalised_file(filename: str):
  if (not (isinstance(filename, str) and filename.endswith(".mp3"))):
    raise ValueError("Invalid filename given.")

  # Already normalised.
  if filename.endswith("-normalised.mp3"):
    return filename

  normalised_filename = "{}-normalised.mp3".format(filename.rsplit(".",1)[0])

  # The file already exists, short circuit.
  if (os.path.exists(normalised_filename)):
    return normalised_filename

  sound = AudioSegment.from_file(filename, "mp3")
  normalised_sound = effects.normalize(sound) #match_target_amplitude(sound, -10)

  normalised_sound.export(normalised_filename, bitrate="320k", format="mp3")
  return normalised_filename

# Returns either a normalised file path (based on filename), or the original if not available.
def get_normalised_filename_if_available(filename:str):
  if (not (isinstance(filename, str) and filename.endswith(".mp3"))):
    raise ValueError("Invalid filename given.")

  # Already normalised.
  if filename.endswith("-normalised.mp3"):
    return filename


  normalised_filename = "{}-normalised.mp3".format(filename.rstrip(".mp3"))

  # normalised version exists
  if (os.path.exists(normalised_filename)):
    return normalised_filename

  # Else we've not got a normalised verison, just take original.
  return filename

