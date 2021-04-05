import logging
from logging.handlers import RotatingFileHandler
from helpers.os_environment import resolve_external_file_path
import os

LOG_MAX_SIZE_MB = 20
LOG_BACKUP_COUNT = 4

class LoggingManager():

    logger: logging.Logger

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)


        logpath: str = resolve_external_file_path("/logs")
        if not os.path.isdir(logpath):
            try:
                # Try creating the directory.
                os.mkdir(logpath)
            except:
                print("Failed to create log directory.")
                return

        filename: str = resolve_external_file_path("/logs/" + name + ".log")

        if not os.path.isfile(filename):
            try:
                # Try creating the file.
                open(filename, "x")
            except:
                print("Failed to create log file.")
                return


        self.logger.setLevel(logging.INFO)
        fh = RotatingFileHandler(filename, maxBytes=LOG_MAX_SIZE_MB*(1024**2), backupCount=LOG_BACKUP_COUNT)
        formatter = logging.Formatter('%(asctime)s  | %(levelname)s | %(message)s')
        fh.setFormatter(formatter)
        # add the handler to the logger
        self.logger.addHandler(fh)
        self.logger.info("** LOGGER STARTED **")

    #def __del__(self):
        # Can't seem to close logger properly
        #self.logger.info("** LOGGER EXITING **")

    @property
    def log(self) -> logging.Logger:
        return self.logger
