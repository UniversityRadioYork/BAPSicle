from pydub import AudioSegment
import os
import math
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

def generate_peaks_from_filename(filename: str):
  if not (isinstance(filename, str) and filename.endswith(".mp3")):
    raise ValueError("Invalid filename given.")

  audio: AudioSegment = AudioSegment.from_file(filename, "mp3")

  # Returns the raw audio data as an array of (numeric) samples.
  # Note: if the audio has multiple channels, the samples for each channel will be serialized
  # for example, stereo audio would look like [sample_1_L, sample_1_R, sample_2_L, sample_2_R, …].
  samples: list[int] = list(audio.get_array_of_samples())

  channels: int = audio.channels if audio.channels else 1
  samples_per_channel = [[]]*channels



  if not samples:
    return []

  if channels > 0:
    for channel in range(channels):
      samples_per_channel[channel] = samples[channel::channels]






  number_of_segments = math.floor(len(samples)/2205)
  first = 0
  last = math.floor(number_of_segments - 1)


  sampleSize = math.floor(len(samples) / number_of_segments)
  sampleStep = max(math.floor(sampleSize / 10),1)

  peak_entries_per_channel = int(sampleSize*2/channels)

  peaks_per_channel = [[0]*peak_entries_per_channel]*channels
  c = 0
  merged_peaks = [0]*(peak_entries_per_channel*channels)


  for c in range(channels):
      peaks = [0]*peak_entries_per_channel
      chan = samples_per_channel[c]

      for i in range(first,last):
          start = math.floor(i * sampleSize)
          end = min(len(chan)-1, math.floor(start + sampleSize))
          if start > len(chan):
            break
          minimum = chan[start]
          maximum = minimum

          for j in range(start, end, sampleStep):
              value = chan[j]

              if (value > maximum):
                  maximum = value

              if (value < maximum):
                  minimum = value

          if 2*i+1 >= len(peaks):
            break
          if peaks[2 * i] != 0:
            raise Exception("Overwriting peaks at ", 2 * i)
          peaks[2 * i] = maximum
          peaks[2 * i + 1] = minimum

          if (c == 0 or maximum > merged_peaks[2 * i]):
            merged_peaks[2 * i] = maximum

          if (c == 0 or minimum< merged_peaks[2 * i + 1]):
            merged_peaks[2 * i + 1] = minimum
      peaks_per_channel[c] = peaks

  merged = True
  return {
    "sample_rate": audio.frame_rate,
    "number_of_segments": number_of_segments,
    "version":2,
    "channels":channels,
    "samples": len(samples),
    "samples_per_segment":sampleSize,
    "bits": 8,
    "length": len(merged_peaks) if merged else len(peaks_per_channel[0]),
    "data": merged_peaks if merged else peaks_per_channel
  }

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


