import logging
import sys
from logging import LogRecord
from traceback import TracebackException

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
                line = "<span class='" + style + \
                    "'>" + self.format(item) + "</span>"
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
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s %(message)s', '%m-%d %H:%M:%S')
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

    def formatException(self, e: Exception) -> str:
        trace = None
        if (hasattr(e, "__traceback__")):
            trace = e.__traceback__
        tbe = TracebackException(type(e), e, trace, limit=None)
        lines = list(self._format(tbe))
        return'\n%s' % ''.join(lines)

    def _format(self, tbe):
        if (tbe.__context__ is not None and not tbe.__suppress_context__):
            yield from self._format(tbe.__context__)
            yield "Whose handling caused:\n"
        is_addon, stack = self._formatStack(tbe)
        yield from stack
        yield from tbe.format_exception_only()

    def _formatStack(self, tbe):
        _RECURSIVE_CUTOFF = 3
        result = []
        last_file = None
        last_line = None
        last_name = None
        count = 0
        is_addon = False
        buffer = []
        for frame in tbe.stack:
            line_internal = True
            if (last_file is None or last_file != frame.filename or last_line is None or last_line != frame.lineno or last_name is None or last_name != frame.name):
                if count > _RECURSIVE_CUTOFF:
                    count -= _RECURSIVE_CUTOFF
                    result.append(
                        f'  [Previous line repeated {count} more '
                        f'time{"s" if count > 1 else ""}]\n'
                    )
                last_file = frame.filename
                last_line = frame.lineno
                last_name = frame.name
                count = 0
            count += 1
            if count > _RECURSIVE_CUTOFF:
                continue
            fileName = frame.filename
            pos = fileName.rfind("hassio-google-drive-backup/backup")
            if pos > 0:
                is_addon = True
                line_internal = False
                fileName = "/addon" + \
                    fileName[pos + len("hassio-google-drive-backup/backup"):]

            pos = fileName.rfind("site-packages")
            if pos > 0:
                fileName = fileName[pos - 1:]

            pos = fileName.rfind("python3.7")
            if pos > 0:
                fileName = fileName[pos - 1:]
                pass
            line = '  {}:{} ({})\n'.format(fileName, frame.lineno, frame.name)
            if line_internal:
                buffer.append(line)
            else:
                result.extend(self._compressFrames(buffer))
                buffer = []
                result.append(line)
        if count > _RECURSIVE_CUTOFF:
            count -= _RECURSIVE_CUTOFF
            result.append(
                f'  [Previous line repeated {count} more '
                f'time{"s" if count > 1 else ""}]\n'
            )
        result.extend(self._compressFrames(buffer))
        return is_addon, result

    def _compressFrames(self, buffer):
        if len(buffer) > 1:
            yield buffer[0]
            if len(buffer) == 3:
                yield buffer[1]
            elif len(buffer) > 2:
                yield "  [{} hidden frames]\n".format(len(buffer) - 2)
            yield buffer[len(buffer) - 1]
        elif len(buffer) > 0:
            yield buffer[len(buffer) - 1]
            pass
