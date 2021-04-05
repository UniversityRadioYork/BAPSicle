from queue import Empty
import unittest
import multiprocessing
import time


from player import Player
from helpers.logging_manager import LoggingManager
# How long to wait (by default) in secs for the player to respond.
TIMEOUT_MSG_MAX_S = 10
TIMEOUT_QUIT_S = 10
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
        self.player = multiprocessing.Process(target=Player, args=(-1, self.player_to_q, self.player_from_q))
        self.player.start()

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

    def _wait_for_msg(self, msg: str, sources_filter=["TEST"], timeout:int = TIMEOUT_MSG_MAX_S):
        elapsed = 0
        got_anything = False
        while elapsed < timeout:
            try:
                response: str = self.player_from_q.get_nowait()
                if response:
                    self.logger.log.info("Received response: {}\nWas looking for {}:{}".format(response, sources_filter, msg))
                    got_anything = True
                    source = response[:response.index(":")]
                    if source in sources_filter:
                        if response.startswith("TEST:"+msg):
                            return response[len("TEST:"+msg):]
            except Empty:
                pass
            finally:
                time.sleep(0.1)
                elapsed += 0.1
        return False if got_anything else None

    def _send_msg_and_wait(self, msg:str, sources_filter=["TEST"], timeout: int = TIMEOUT_MSG_MAX_S):
        self._send_msg(msg)
        return self._wait_for_msg(msg, sources_filter, timeout)


    def test_player_running(self):
        response = self._send_msg_and_wait("STATUS")

        # assert the status code of the response
        self.assertTrue(response)


# runs the unit tests in the module
if __name__ == '__main__':
    try:
        unittest.main()
    except Exception as e:
        print("Tests failed :/", e)
    else:
        print("Tests passed!")
