import os
from pydub import AudioSegment, effects  # Audio leveling!

# Stuff to help make BAPSicle play out leveled audio.

# Takes filename in, normalialises it and returns a normalised file path.


def generate_normalised_file(filename: str):
    if not (isinstance(filename, str) and filename.endswith(".mp3")):
        raise ValueError("Invalid filename given.")

    # Already normalised.
    if filename.endswith("-normalised.mp3"):
        return filename

    normalised_filename = "{}-normalised.mp3".format(filename.rsplit(".", 1)[0])

    # The file already exists, short circuit.
    if os.path.exists(normalised_filename):
        return normalised_filename

    sound = AudioSegment.from_file(filename, "mp3")
    normalised_sound = effects.normalize(sound)

    normalised_sound.export(normalised_filename, bitrate="320k", format="mp3")
    return normalised_filename


# Returns either a normalised file path (based on filename), or the original if not available.
def get_normalised_filename_if_available(filename: str):
    if not (isinstance(filename, str) and filename.endswith(".mp3")):
        raise ValueError("Invalid filename given.")

    # Already normalised.
    if filename.endswith("-normalised.mp3"):
        return filename

    normalised_filename = "{}-normalised.mp3".format(filename.rstrip(".mp3"))

    # normalised version exists
    if os.path.exists(normalised_filename):
        return normalised_filename

    # Else we've not got a normalised verison, just take original.
    return filename
