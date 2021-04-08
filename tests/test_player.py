from queue import Empty
import unittest
import multiprocessing
import time
import os
import json

from player import Player
from helpers.logging_manager import LoggingManager

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
    return str(json.dumps(getPlanItem(length, weight)))


class TestPlayer(unittest.TestCase):

    player: multiprocessing.Process
    player_from_q: multiprocessing.Queue
    player_to_q: multiprocessing.Queue
    logger: LoggingManager

    # initialization logic for the test suite declared in the test module
    # code that is executed before all tests in one test run
    @classmethod
    def setUpClass(cls):
        cls.logger = LoggingManager("Test_Player")

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
            target=Player, args=(-1, self.player_to_q, self.player_from_q)
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
                            len(source + ":" + msg) + 1 :
                        ]  # +1 to remove trailing : on source.
            except Empty :
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
    ):
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

        time.sleep(0.5)
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


# runs the unit tests in the module
if __name__ == "__main__":
    unittest.main()
