from typing import Optional
from queue import Empty
import unittest
import multiprocessing
import time
import os
import json

from player import Player
from helpers.logging_manager import LoggingManager
from helpers.state_manager import StateManager
from helpers.os_environment import isMacOS

# How long to wait (by default) in secs for the player to respond.
TIMEOUT_MSG_MAX_S = 10
TIMEOUT_QUIT_S = 10

test_dir = dir_path = os.path.dirname(os.path.realpath(__file__)) + "/"
resource_dir = test_dir + "resources/"


# All because constant dicts are still mutable in python :/
def getPlanItem(length: int, weight: int):
    if length not in [1, 2, 5]:
        raise ValueError("Invalid length dummy planitem.")
    # TODO: This assumes we're handling one channel where timeslotitemid is unique
    item = {
        "timeslotitemid": weight,
        "managedid": str(length),
        "filename": resource_dir + str(length) + "sec.mp3",
        "weight": weight,
        "title": str(length) + "sec",
        "length": "00:00:0{}".format(length),
    }
    return item


def getPlanItemJSON(length: int, weight: int):
    return str(json.dumps(getPlanItem(**locals())))


# All because constant dicts are still mutable in python :/
def getMarker(name: str, time: float, position: str, section: Optional[str] = None):
    # Time is not validated here, to allow tests to check server response.
    marker = {
        "name": name,  # User friendly name, eg. "Hit the vocals"
        "time": time,  # Position (secs) through item
        "section": section,  # for linking in loops, if none, assume intro, cue, outro based on "position"
        "position": position,  # start, mid, end
    }
    return marker


def getMarkerJSON(name: str, time: float, position: str, section: Optional[str] = None):
    return json.dumps(getMarker(**locals()))


class TestPlayer(unittest.TestCase):

    player: multiprocessing.Process
    player_from_q: multiprocessing.Queue
    player_to_q: multiprocessing.Queue
    logger: LoggingManager
    server_state: StateManager

    # initialization logic for the test suite declared in the test module
    # code that is executed before all tests in one test run
    @classmethod
    def setUpClass(cls):
        cls.logger = LoggingManager("Test_Player")
        cls.server_state = StateManager(
            "BAPSicleServer", cls.logger, default_state={"tracklist_mode": "off"}
        )  # Mostly dummy here.

    # clean up logic for the test suite declared in the test module
    # code that is executed after all tests in one test run
    @classmethod
    def tearDownClass(cls):
        pass

    # initialization logic
    # code that is executed before each test
    def setUp(self):
        self.player_from_q = multiprocessing.Queue()
        self.player_to_q = multiprocessing.Queue()
        self.player = multiprocessing.Process(
            target=Player,
            args=(-1, self.player_to_q, self.player_from_q, self.server_state),
        )
        self.player.start()
        self._send_msg_wait_OKAY("CLEAR")  # Empty any previous track items.
        self._send_msg_wait_OKAY("STOP")
        self._send_msg_wait_OKAY("UNLOAD")
        self._send_msg_wait_OKAY("PLAYONLOAD:False")
        self._send_msg_wait_OKAY("REPEAT:none")
        self._send_msg_wait_OKAY("AUTOADVANCE:True")

    # clean up logic
    # code that is executed after each test
    def tearDown(self):
        # Try to kill it, waits the timeout.
        if self._send_msg_and_wait("QUIT"):
            self.player.join(timeout=TIMEOUT_QUIT_S)
            self.logger.log.info("Player quit successfully.")
        else:
            self.logger.log.error("No response on teardown, terminating player.")
            # It's brain dead :/
            self.player.terminate()

    def _send_msg(self, msg: str):
        self.player_to_q.put("TEST:{}".format(msg))

    def _wait_for_msg(
        self, msg: str, sources_filter=["TEST"], timeout: int = TIMEOUT_MSG_MAX_S
    ):
        elapsed = 0
        got_anything = False
        while elapsed < timeout:
            try:
                response: str = self.player_from_q.get_nowait()
                if response:
                    self.logger.log.info(
                        "Received response: {}\nWas looking for {}:{}".format(
                            response, sources_filter, msg
                        )
                    )
                    got_anything = True
                    source = response[: response.index(":")]
                    if source in sources_filter:
                        return response[
                            len(source + ":" + msg) + 1:
                        ]  # +1 to remove trailing : on source.
            except Empty:
                pass
            finally:
                time.sleep(0.01)
                elapsed += 0.01
        return False if got_anything else None

    def _send_msg_and_wait(
        self, msg: str, sources_filter=["TEST"], timeout: int = TIMEOUT_MSG_MAX_S
    ):
        self._send_msg(msg)
        return self._wait_for_msg(msg, sources_filter, timeout)

    def _send_msg_wait_OKAY(
        self, msg: str, sources_filter=["TEST"], timeout: int = TIMEOUT_MSG_MAX_S
    ) -> Optional[str]:
        response = self._send_msg_and_wait(msg, sources_filter, timeout)

        self.assertTrue(response)

        self.assertTrue(isinstance(response, str))

        response = response.split(":", 1)

        self.assertEqual(response[0], "OKAY")

        if len(response) > 1:
            return response[1]
        return None

    def test_player_running(self):
        response = self._send_msg_wait_OKAY("STATUS")

        self.assertTrue(response)

        json_obj = json.loads(response)

        self.assertTrue(json_obj["initialised"])

    def test_player_play(self):

        response = self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(2, 0))

        # Should return nothing, just OKAY.
        self.assertFalse(response)

        # Check we can load the file
        response = self._send_msg_wait_OKAY("LOAD:0")
        self.assertFalse(response)

        # Check we can play the file
        response = self._send_msg_wait_OKAY("PLAY")
        self.assertFalse(response)

        time.sleep(1)

        response = self._send_msg_wait_OKAY("STATUS")

        self.assertTrue(response)

        json_obj = json.loads(response)

        self.assertTrue(json_obj["playing"])

        # Check the file stops playing.
        # TODO: Make sure replay / play on load not enabled.
        time.sleep(2)

        response = self._send_msg_wait_OKAY("STATUS")

        self.assertTrue(response)

        json_obj = json.loads(response)

        self.assertFalse(json_obj["playing"])

    # This test checks if the player progresses to the next item and plays on load.
    def test_play_on_load(self):
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 0))

        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 1))

        self._send_msg_wait_OKAY("PLAYONLOAD:True")

        self._send_msg_wait_OKAY("LOAD:0")

        # We should be playing the first item.
        response = self._send_msg_wait_OKAY("STATUS")
        self.assertTrue(response)
        json_obj = json.loads(response)
        self.assertTrue(json_obj["playing"])
        self.assertEqual(json_obj["loaded_item"]["weight"], 0)

        time.sleep(5)

        # Now we should be onto playing the second item.
        response = self._send_msg_wait_OKAY("STATUS")
        self.assertTrue(response)
        json_obj = json.loads(response)
        self.assertTrue(json_obj["playing"])
        self.assertEqual(json_obj["loaded_item"]["weight"], 1)

        # Okay, now stop. Test if play on load causes havok with auto advance.
        self._send_msg_wait_OKAY("STOP")
        self._send_msg_wait_OKAY("AUTOADVANCE:False")
        self._send_msg_wait_OKAY("LOAD:0")

        time.sleep(6)

        # Now, we've not auto-advanced, but we've not loaded a new item.
        # Therefore, we shouldn't have played a second time. Leave repeat-one for that.
        response = self._send_msg_wait_OKAY("STATUS")
        self.assertTrue(response)
        json_obj = json.loads(response)
        self.assertFalse(json_obj["playing"])
        self.assertEqual(json_obj["loaded_item"]["weight"], 0)

    # This test checks that the player repeats the first item without moving onto the second.
    def test_repeat_one(self):
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 0))
        # Add a second item to make sure we don't load this one when repeat one.
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 1))

        # TODO Test without play on load? What's the behaviour here?
        self._send_msg_wait_OKAY("PLAYONLOAD:True")
        self._send_msg_wait_OKAY("REPEAT:one")

        self._send_msg_wait_OKAY("LOAD:0")

        time.sleep(0.5)

        # Try 3 repeats to make sure.
        for repeat in range(3):
            # We should be playing the first item.
            response = self._send_msg_wait_OKAY("STATUS")
            self.assertTrue(response)
            json_obj = json.loads(response)
            self.assertTrue(json_obj["playing"])
            # Check we're not playing the second item.
            self.assertEqual(json_obj["loaded_item"]["weight"], 0)

            time.sleep(5)

    # This test checks that the player repeats all plan items before playing the first again.
    def test_repeat_all(self):
        # Add two items to repeat all between
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 0))
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 1))

        # TODO Test without play on load? What's the behaviour here?
        self._send_msg_wait_OKAY("PLAYONLOAD:True")
        self._send_msg_wait_OKAY("REPEAT:all")

        self._send_msg_wait_OKAY("LOAD:0")

        time.sleep(1)
        # Try 3 repeats to make sure.
        for repeat in range(3):
            # We should be playing the first item.
            response = self._send_msg_wait_OKAY("STATUS")
            self.assertTrue(response)
            json_obj = json.loads(response)
            self.assertTrue(json_obj["playing"])
            self.assertEqual(json_obj["loaded_item"]["weight"], 0)

            time.sleep(5)

            # We should be playing the second item.
            response = self._send_msg_wait_OKAY("STATUS")
            self.assertTrue(response)
            json_obj = json.loads(response)
            self.assertTrue(json_obj["playing"])
            self.assertEqual(json_obj["loaded_item"]["weight"], 1)

            time.sleep(5)

    # TODO: Test validation of trying to break this.
    # TODO: Test cue behaviour.
    def test_markers(self):
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 0))
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 1))
        self._send_msg_wait_OKAY("ADD:" + getPlanItemJSON(5, 2))

        self._send_msg_wait_OKAY("LOAD:2")  # To test currently loaded marker sets.

        markers = [
            # Markers are stored as float, to compare against later,
            # these must all be floats, despite int being supported.
            getMarkerJSON("Intro Name", 2.0, "start", None),
            getMarkerJSON("Cue Name", 3.14, "mid", None),
            getMarkerJSON("Outro Name", 4.0, "end", None),
            getMarkerJSON("Start Loop", 2.0, "start", "The Best Loop 1"),
            getMarkerJSON("Mid Loop", 3.0, "mid", "The Best Loop 1"),
            getMarkerJSON("End Loop", 3.5, "end", "The Best Loop 1"),
        ]
        # Command, Weight?/itemid? (-1 is loaded), marker json (Intro at 2 seconds.)
        self._send_msg_wait_OKAY("SETMARKER:0:" + markers[0])
        self._send_msg_wait_OKAY("SETMARKER:0:" + markers[1])
        self._send_msg_wait_OKAY("SETMARKER:1:" + markers[2])
        self._send_msg_wait_OKAY("SETMARKER:-1:" + markers[3])
        self._send_msg_wait_OKAY("SETMARKER:-1:" + markers[4])
        self._send_msg_wait_OKAY("SETMARKER:-1:" + markers[5])

        # Test we didn't completely break the player
        response = self._send_msg_wait_OKAY("STATUS")
        self.assertTrue(response)
        json_obj = json.loads(response)
        self.logger.log.warning(json_obj)

        # time.sleep(1000000)
        # Now test that all the markers we setup are present.
        item = json_obj["show_plan"][0]
        self.assertEqual(item["weight"], 0)
        self.assertEqual(
            item["intro"], 2.0
        )  # Backwards compat with basic Webstudio intro/cue/outro
        self.assertEqual(item["cue"], 3.14)
        self.assertEqual(
            [json.dumps(item) for item in item["markers"]], markers[0:2]
        )  # Check the full marker configs match

        item = json_obj["show_plan"][1]
        self.assertEqual(item["weight"], 1)
        self.assertEqual(item["outro"], 4.0)
        self.assertEqual([json.dumps(item) for item in item["markers"]], [markers[2]])

        # In this case, we want to make sure both the current and loaded items are updated
        for item in [json_obj["show_plan"][2], json_obj["loaded_item"]]:
            self.assertEqual(item["weight"], 2)
            # This is a loop marker. It should not appear as a standard intro, outro or cue.
            # Default of 0.0 should apply to all.
            self.assertEqual(item["intro"], 0.0)
            self.assertEqual(item["outro"], 0.0)
            self.assertEqual(item["cue"], 0.0)
            self.assertEqual(
                [json.dumps(item) for item in item["markers"]], markers[3:]
            )

        # TODO: Now test editing/deleting them


# runs the unit tests in the module
if __name__ == "__main__":
    # Fixes fork error.
    if isMacOS():
        multiprocessing.set_start_method("spawn", True)
    unittest.main()
