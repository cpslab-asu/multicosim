import logging
import time

from multicosim import containers


@containers.server(msgtype=int)
def sleep(duration: int):
    logger = logging.getLogger("server")
    logger.addHandler(logging.NullHandler())
    logger.info("Received command to wait for %d seconds", duration)
    time.sleep(duration)
    logger.info("Duration reached, shutting down")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sleep.listen(5556)
