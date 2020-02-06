import logging
from logging import LogRecord
import sys

HISTORY_SIZE = 1000


class HistoryHandler(logging.Handler):
    def __init__(self):
        super(HistoryHandler, self).__init__()
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def reset(self):
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def emit(self, record: LogRecord):
        self.history[self.history_index % HISTORY_SIZE] = record
        self.history_index += 1

    def getHistory(self, start=0, html=False):
        end = self.history_index
        if end - start >= HISTORY_SIZE:
            start = end - HISTORY_SIZE
        for x in range(start, end):
            item = self.history[x % HISTORY_SIZE]
            if html:
                if item.levelno == logging.WARN:
                    style = "console-warning"
                elif item.levelno == logging.ERROR:
                    style = "console-error"
                elif item.levelno == logging.DEBUG:
                    style = "console-debug"
                elif item.levelno == logging.CRITICAL:
                    style = "console-critical"
                elif item.levelno == logging.FATAL:
                    style = "console-fatal"
                elif item.levelno == logging.WARNING:
                    style = "console-warning"
                else:
                    style = "console-default"
                line = "<span class='" + style + "'>" + self.format(item) + "</span>"
                yield (x + 1, line)
            else:
                yield (x + 1, self.format(item))

    def getLast(self) -> LogRecord:
        return self.history[(self.history_index - 1) % HISTORY_SIZE]


class ColorHandler(logging.Handler):
    def __init__(self):
        super(ColorHandler, self).__init__()

    def emit(self, record: logging.LogRecord):
        sys.stdout.write(self.format(record) + "\n")


logger: logging.Logger = logging.getLogger("appwide")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%m-%d %H:%M:%S')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

history_handler = HistoryHandler()
history_handler.setLevel(logging.DEBUG)
history_handler.setFormatter(formatter)
logger.addHandler(history_handler)
logging.getLogger("cherrypy.error").addHandler(history_handler)
logging.getLogger("cherrypy.error").addHandler(console_handler)
logging.getLogger("cherrypy.error").setLevel(logging.WARNING)


class LogBase(object):

    def info(self, message: str) -> None:
        logger.info(message)

    def debug(self, message: str) -> None:
        logger.debug(message)

    def error(self, message: str) -> None:
        logger.error(message)

    def warn(self, message: str) -> None:
        logger.warning(message)

    def critical(self, message: str) -> None:
        logger.critical(message)

    def setConsoleLevel(self, level) -> None:
        console_handler.setLevel(level)

    @classmethod
    def getHistory(cls, index, html):
        return history_handler.getHistory(index, html)

    @classmethod
    def getLast(cls) -> LogRecord:
        return history_handler.getLast()

    @classmethod
    def reset(cls) -> None:
        return history_handler.reset()
