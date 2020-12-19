import logging
from helpers.os_environment import resolve_external_file_path
import os


class LoggingManager():

    logger: logging.Logger

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

        filename: str = resolve_external_file_path("/logs/" + name + ".log")

        if not os.path.isfile(filename):
            try:
                # Try creating the file.
                open(filename, "x")
            except:
                print("Failed to create log file")
                return

        logging.basicConfig(
            filename=filename,
            format='%(asctime)s  | %(levelname)s | %(message)s',
            level=logging.INFO,
            filemode='a'
        )
        self.logger.info("** LOGGER STARTED **")

    def __del__(self):
        self.logger.info("** LOGGER EXITING **")
        logging.shutdown()

    @property
    def log(self) -> logging.Logger:
        return self.logger
