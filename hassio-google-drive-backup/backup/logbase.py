import logging

HISTORY_SIZE = 1000


class HistoryHandler(logging.Handler):
    def __init__(self):
        super(HistoryHandler, self).__init__()
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def emit(self, record):
        self.history[self.history_index] = self.format(record)
        self.history_index = (self.history_index + 1) % HISTORY_SIZE

    def getHistory(self):
        for x in range(HISTORY_SIZE):
            yield self.history[(self.history_index + x) % HISTORY_SIZE]


logger: logging.Logger = logging.getLogger("appwide")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

history_handler = HistoryHandler()
history_handler.setLevel(logging.DEBUG)
history_handler.setFormatter(formatter)
logger.addHandler(history_handler)


class LogBase(object):

    def info(self, message: str) -> None:
        logger.info(message)

    def debug(self, message: str) -> None:
        logger.debug(message)

    def error(self, message: str) -> None:
        logger.error(message)

    def warn(self, message: str) -> None:
        logger.warn(message)

    def critical(self, message: str) -> None:
        logger.critical(message)

    def setConsoleLevel(self, level) -> None:
        console_handler.setLevel(level)

    def getHistory(self):
        return history_handler.getHistory()
