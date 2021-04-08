from multiprocessing import Queue
from typing import Callable, List


class Controller:
    # Main controller class. All implementations of controller support should inherit this.
    callbacks: List[Callable] = []
    player_to_q: List[Queue]
    player_from_q: List[Queue]

    def __init__(self, player_to_q: List[Queue], player_from_q: List[Queue]):
        self.handler()
        return

    def _state_handler(self):
        return

    # Registers a function for the controller class to call to tell BAPSicle to do something.
    def register_callback(self, callback: Callable):
        self.callbacks.append(callback)
        return

    # Loop etc in here to process the data from your controller and call the callbacks.
    def handler(self):
        return
