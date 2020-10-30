import logging
from helpers.os_environment import resolve_external_file_path


class LoggingManager():

    logger = None

    def __init__(self, name):
        self.logger = logging.getLogger(name)

        logging.basicConfig(
            filename=resolve_external_file_path("/logs/" + name + ".txt"),
            format='%(asctime)s  | %(levelname)s | %(message)s',
            level=logging.INFO,
            filemode='a'
        )
        self.logger.info("** LOGGER STARTED **")

    def __del__(self):
        self.logger.info("** LOGGER EXITING **")
        logging.shutdown()

    @property
    def log(self):
        return self.logger
