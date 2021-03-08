import re
from datetime import timedelta
from injector import inject, singleton

SECOND_IDENTIFIERS = ["s", "sec", "secs", "second", "seconds"]
MINUTE_IDENTIFIERS = ["m", "min", "mins", "minute", "minutes"]
HOUR_IDENTIFIERS = ["h", "hr", "hour", "hours"]
DAY_IDENTIFIERS = ["d", "day", "days"]
NUMBER_REGEX = "^([0-9]*[.])?[0-9]+"
VALID_REGEX = "^([ ]*([0-9]*[.])?[0-9]+[ ]*(seconds|second|secs|sec|s|minutes|minute|mins|min|m|hours|hour|hr|h|days|day|d)?[ ,]*)*"


@singleton
class DurationParser():
    @inject
    def __init__(self):
        pass

    def parse(self, source: str):
        source = source.lower()
        total_match = re.match(VALID_REGEX, source)
        if not total_match or total_match.group(0) != source:
            raise ValueError()
        parts = source.split()
        i = 0
        total = timedelta(seconds=0)
        while (i < len(parts)):
            part = parts[i].strip().strip(',')
            match = re.match(NUMBER_REGEX, part)
            i += 1
            if not match:
                raise ValueError()
            length = float(match.group(0))
            if match.group(0) == part:

                if i < len(parts):
                    next_part = parts[i].strip().strip(',')
                    if next_part in SECOND_IDENTIFIERS or next_part in MINUTE_IDENTIFIERS or next_part in HOUR_IDENTIFIERS or next_part in DAY_IDENTIFIERS:
                        identifier = next_part
                        i += 1
                    else:
                        identifier = SECOND_IDENTIFIERS[0]
                else:
                    identifier = "s"
            else:
                identifier = part[len(match.group(0)):]
            if identifier in SECOND_IDENTIFIERS:
                total += timedelta(seconds=length)
            elif identifier in MINUTE_IDENTIFIERS:
                total += timedelta(minutes=length)
            elif identifier in HOUR_IDENTIFIERS:
                total += timedelta(hours=length)
            elif identifier in DAY_IDENTIFIERS:
                total += timedelta(days=length)
            else:
                raise ValueError()
        return total

    def format(self, duration: timedelta):
        parts = []
        if duration >= timedelta(days=1):
            days = int(duration.days)
            parts.append("{} days".format(days))
            duration = duration - timedelta(days=days)
        if duration >= timedelta(hours=1):
            hours = int(duration.seconds / (60 * 60))
            parts.append("{} hours".format(hours))
            duration = duration - timedelta(hours=hours)
        if duration >= timedelta(minutes=1):
            minutes = int(duration.seconds / 60)
            parts.append("{} minutes".format(minutes))
            duration = duration - timedelta(minutes=minutes)
        if duration >= timedelta(seconds=1):
            seconds = int(duration.seconds)
            parts.append("{} seconds".format(seconds))
            duration = duration - timedelta(seconds=seconds)
        if len(parts) > 0:
            return ", ".join(parts)
        else:
            return "0 seconds"
