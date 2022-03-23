import re
from injector import inject, singleton

SECOND_IDENTIFIERS = ["s", "sec", "secs", "second", "seconds"]
MINUTE_IDENTIFIERS = ["m", "min", "mins", "minute", "minutes"]
HOUR_IDENTIFIERS = ["h", "hr", "hour", "hours"]
DAY_IDENTIFIERS = ["d", "day", "days"]
NUMBER_REGEX = "^([0-9]*[.])?[0-9]+"
VALID_REGEX = "^[ ]*([0-9,]*\\.?[0-9]*)[ ]*(b|B|k|K|m|M|g|G|t|T|p|P|e|E|z|Z|y|Y)[a-zA-Z ]*[ ]*$"
BYTES_BASE = 1024
PREFIX_VALUES = {
    "b": 1,
    "k": BYTES_BASE,
    "m": pow(BYTES_BASE, 2),
    "g": pow(BYTES_BASE, 3),
    "t": pow(BYTES_BASE, 4),
    "p": pow(BYTES_BASE, 5),
    "e": pow(BYTES_BASE, 6),
    "z": pow(BYTES_BASE, 7),
    "y": pow(BYTES_BASE, 8)
}

PREFIX_CANONICAL = ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]


@singleton
class ByteFormatter():
    @inject
    def __init__(self):
        pass

    def parse(self, source: str):
        source = source.lower()
        match = re.match(VALID_REGEX, source.lower())
        if not match:
            raise ValueError()
        number, prefix = match.group(1, 2)
        if prefix not in PREFIX_VALUES:
            raise ValueError()

        return float(number) * PREFIX_VALUES[prefix]

    def format(self, bytes):
        for prefix in PREFIX_CANONICAL:
            if bytes < BYTES_BASE:
                if int(bytes) == bytes:
                    return f"{int(bytes)} {prefix}B"
                else:
                    return f"{bytes} {prefix}B"
            bytes /= BYTES_BASE

        bytes *= BYTES_BASE
        if int(bytes) == bytes:
            return f"{int(bytes)} YB"
        else:
            return f"{bytes} YB"
