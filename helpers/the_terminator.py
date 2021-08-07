# Based on https://stackoverflow.com/questions/18499497/how-to-process-sigterm-signal-gracefully

import signal


class Terminator:
    terminate = False

    def __init__(self):
        pass
        #signal.signal(signal.SIGINT, self.exit_gracefully)
        #signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        #self.terminate = True
        pass
