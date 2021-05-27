# see
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
logging.basicConfig(filename="bapsicle_log.log", level=logging.INFO)
logging.info("Started Logging")
