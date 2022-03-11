from helpers.state_manager import StateManager
from helpers.os_environment import isWindows, resolve_external_file_path
from typing import List
from setproctitle import setproctitle
from multiprocessing import current_process, Queue
from time import sleep
import os
import json
from syncer import sync

from helpers.logging_manager import LoggingManager
from helpers.the_terminator import Terminator
from helpers.myradio_api import MyRadioAPI
from helpers.normalisation import generate_normalised_file
from baps_types.plan import PlanItem


class FileManager:
    logger: LoggingManager
    api: MyRadioAPI

    def __init__(self, channel_from_q: Queue, server_config: StateManager):

        self.logger = LoggingManager("FileManager")
        self.api = MyRadioAPI(self.logger, server_config)

        process_title = "File Manager"
        setproctitle(process_title)
        current_process().name = process_title

        terminator = Terminator()
        self.normalisation_mode = server_config.get()["normalisation_mode"]
        if self.normalisation_mode != "on":
            self.logger.log.info("Normalisation is disabled.")
        else:
            self.logger.log.info("Normalisation is enabled.")
        self.channel_count = server_config.get()["num_channels"]
        self.channel_received = None
        self.last_known_show_plan = [[]] * self.channel_count
        self.next_channel_preload = 0
        self.known_channels_preloaded = [False] * self.channel_count
        self.known_channels_normalised = [False] * self.channel_count
        self.last_known_item_ids = [[]] * self.channel_count
        try:

            while not terminator.terminate:
                # If all channels have received the delete command, reset for the next one.
                if (
                    self.channel_received is None
                    or self.channel_received == [True] * self.channel_count
                ):
                    self.channel_received = [False] * self.channel_count

                try:
                    message = channel_from_q.get_nowait()
                except Exception:
                    # No new messages
                    # Let's try preload / normalise some files now we're free of messages.
                    preloaded = self.do_preload()
                    normalised = self.do_normalise()

                    if not preloaded and not normalised:
                        # We didn't do any hard work, let's sleep.
                        sleep(0.2)
                else:
                    try:

                        split = message.split(":", 1)

                        channel = int(split[0])
                        # source = split[1]
                        command = split[2]

                        # If we have requested a new show plan, empty the music-tmp directory for the previous show.
                        if command == "GETPLAN":

                            if (
                                self.channel_received != [
                                    False] * self.channel_count
                                and self.channel_received[channel] is False
                            ):
                                # We've already received a delete trigger on a channel,
                                # let's not delete the folder more than once.
                                # If the channel was already in the process of being deleted, the user has
                                # requested it again, so allow it.

                                self.channel_received[channel] = True
                                continue

                            # Delete the previous show files!
                            # Note: The players load into RAM. If something is playing over the load,
                            # the source file can still be deleted.
                            path: str = resolve_external_file_path(
                                "/music-tmp/")

                            if not os.path.isdir(path):
                                self.logger.log.warning(
                                    "Music-tmp folder is missing, not handling."
                                )
                                continue

                            files = [
                                f
                                for f in os.listdir(path)
                                if os.path.isfile(os.path.join(path, f))
                            ]
                            for file in files:
                                if isWindows():
                                    filepath = path + "\\" + file
                                else:
                                    filepath = path + "/" + file
                                self.logger.log.info(
                                    "Removing file {} on new show load.".format(
                                        filepath
                                    )
                                )
                                try:
                                    os.remove(filepath)
                                except Exception:
                                    self.logger.log.warning(
                                        "Failed to remove, skipping. Likely file is still in use."
                                    )
                                    continue
                            self.channel_received[channel] = True
                            self.known_channels_preloaded = [
                                False] * self.channel_count
                            self.known_channels_normalised = [
                                False
                            ] * self.channel_count

                        # If we receive a new status message, let's check for files which have not been pre-loaded.
                        elif command == "STATUS":
                            extra = message.split(":", 4)
                            if extra[3] != "OKAY":
                                continue

                            status = json.loads(extra[4])
                            show_plan = status["show_plan"]
                            item_ids = []
                            for item in show_plan:
                                item_ids += item["timeslotitemid"]

                            # If the new status update has a different order / list of items,
                            # let's update the show plan we know about
                            # This will trigger the chunk below to do the rounds again and preload any new files.
                            if item_ids != self.last_known_item_ids[channel]:
                                self.last_known_item_ids[channel] = item_ids
                                self.last_known_show_plan[channel] = show_plan
                                self.known_channels_preloaded[channel] = False

                    except Exception:
                        self.logger.log.exception(
                            "Failed to handle message {} on channel {}.".format(
                                message, channel
                            )
                        )



        except Exception as e:
            self.logger.log.exception(
                "Received unexpected exception: {}".format(e))
        del self.logger

    # Attempt to preload a file onto disk.
    def do_preload(self):
        channel = self.next_channel_preload

        # All channels have preloaded all files, do nothing.
        if self.known_channels_preloaded == [True] * self.channel_count:
            return False  # Didn't preload anything

        # Right, let's have a quick check in the status for shows without filenames, to preload them.
        # Keep an eye on if we downloaded anything.
        # If we didn't, we know that all items in this channel have been downloaded.
        downloaded_something = False
        for i in range(len(self.last_known_show_plan[channel])):

            item_obj = PlanItem(self.last_known_show_plan[channel][i])

            # We've not downloaded this file yet, let's do that.
            if not item_obj.filename:
                self.logger.log.info(
                    "Checking pre-load on channel {}, weight {}: {}".format(
                        channel, item_obj.weight, item_obj.name
                    )
                )

                # Getting the file name will only pull the new file if the file doesn't
                # already exist, so this is not too inefficient.
                item_obj.filename, did_download = sync(
                    self.api.get_filename(item_obj, True)
                )
                # Alright, we've done one, now let's give back control to process new statuses etc.

                # Save back the resulting item back in regular dict form
                self.last_known_show_plan[channel][i] = item_obj.__dict__

                if did_download:
                    downloaded_something = True
                    self.logger.log.info(
                        "File successfully preloaded: {}".format(
                            item_obj.filename)
                    )
                    break
                else:
                    # We didn't download anything this time, file was already loaded.
                    # Let's try the next one.
                    continue

        # Tell the file manager that this channel is fully downloaded, this is so
        # it can consider normalising once all channels have files.
        self.known_channels_preloaded[channel] = not downloaded_something

        self.next_channel_preload += 1
        if self.next_channel_preload >= self.channel_count:
            self.next_channel_preload = 0

        return downloaded_something

    # If we've preloaded everything, get to work normalising tracks before playback.
    def do_normalise(self):

        if self.normalisation_mode != "on":
            return False

        # Some channels still have files to preload, do nothing.
        if self.known_channels_preloaded != [True] * self.channel_count:
            return False  # Didn't normalise

        # Quit early if all channels are normalised already.
        if self.known_channels_normalised == [True] * self.channel_count:
            return False

        channel = self.next_channel_preload

        normalised_something = False
        # Look through all the show plan files
        for i in range(len(self.last_known_show_plan[channel])):

            item_obj = PlanItem(self.last_known_show_plan[channel][i])

            filename = item_obj.filename
            if not filename:
                self.logger.log.exception(
                    "Somehow got empty filename when all channels are preloaded."
                )
                continue  # Try next song.
            elif not os.path.isfile(filename):
                self.logger.log.exception(
                    "Filename for normalisation does not exist. This is bad."
                )
                continue
            elif "normalised" in filename:
                continue
            # Sweet, we now need to try generating a normalised version.
            try:
                self.logger.log.info(
                    "Normalising on channel {}: {}".format(channel, filename)
                )
                # This will return immediately if we already have a normalised file.
                item_obj.filename = generate_normalised_file(filename)
                # TODO Hacky
                self.last_known_show_plan[channel][i] = item_obj.__dict__
                normalised_something = True
                break  # Now go let another channel have a go.
            except Exception as e:
                self.logger.log.exception(
                    "Failed to generate normalised file.", str(e))
                continue

        self.known_channels_normalised[channel] = not normalised_something

        self.next_channel_preload += 1
        if self.next_channel_preload >= self.channel_count:
            self.next_channel_preload = 0

        return normalised_something
