from pydub import AudioSegment
import os
from helpers.normalisation import get_original_filename_from_normalised

def generate_silence_file(filename: str):
    if not (isinstance(filename, str) and filename.endswith(".mp3")):
        raise ValueError("Invalid filename given.")

    # Already silent.
    if filename.endswith("-dummy.mp3"):
        return filename

    silent_filename = "{}-dummy.mp3".format(filename.rsplit(".", 1)[0])

    # The file already exists, short circuit.
    if os.path.exists(silent_filename):
        return silent_filename

    # Default to a second if the file is unreadable
    duration_millis = 1000

    # TODO Handle missing ffmpeg
    existing: AudioSegment = AudioSegment.from_file(get_original_filename_from_normalised(filename), "mp3")

    if isinstance(existing.duration_seconds, (int, float)) and existing.duration_seconds > 0:
      duration_millis = int(existing.duration_seconds*1000)

    silent_file = AudioSegment.silent(duration=duration_millis, frame_rate=44100)


    silent_file.export(silent_filename, bitrate="64k", format="mp3")
    return silent_filename

# Returns either a silence file path for the UI (based on filename), or the original if not available.
def get_silence_filename_if_available(filename: str):
    if not (isinstance(filename, str) and filename.endswith(".mp3")):
        raise ValueError("Invalid filename given.")

    # Already normalised.
    if filename.endswith("-dummy.mp3"):
        return filename

    silence_filename = "{}-dummy.mp3".format(filename.rstrip(".mp3"))

    # normalised version exists
    if os.path.exists(silence_filename):
        return silence_filename

    #try:
    # generating should be quick, give it a go
    silence_filename = generate_silence_file(filename)
    filename = silence_filename
    #except:
    #  pass
    # Else we've not got a normalised verison, just take original.
    return filename


