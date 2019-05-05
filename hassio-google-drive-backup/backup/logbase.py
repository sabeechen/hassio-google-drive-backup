import logging
import sys

HISTORY_SIZE = 1000


class HistoryHandler(logging.Handler):
    def __init__(self):
        super(HistoryHandler, self).__init__()
        self.history = [None] * HISTORY_SIZE
        self.history_index = 0

    def emit(self, record):
        self.history[self.history_index % HISTORY_SIZE] = (record.levelno, self.format(record))
        self.history_index += 1

    def getHistory(self, start=0, html=False):
        end = self.history_index
        if end - start >= HISTORY_SIZE:
            start = end - HISTORY_SIZE
        for x in range(start, end):
            item = self.history[x % HISTORY_SIZE]
            if html:
                if item[0] == logging.WARN:
                    style = "console-warning"
                elif item[0] == logging.ERROR:
                    style = "console-error"
                elif item[0] == logging.DEBUG:
                    style = "console-debug"
                elif item[0] == logging.CRITICAL:
                    style = "console-critical"
                elif item[0] == logging.FATAL:
                    style = "console-fatal"
                elif item[0] == logging.WARNING:
                    style = "console-warning"
                else:
                    style = "console-default"
                line = "<span class='" + style + "'>" + item[1] + "</span>"
                yield (x + 1, line)
            else:
                yield (x + 1, item[1])


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
        logger.warn(message)

    def critical(self, message: str) -> None:
        logger.critical(message)

    def setConsoleLevel(self, level) -> None:
        console_handler.setLevel(level)

    def getHistory(self, index, html):
        return history_handler.getHistory(index, html)
