STAGING_KEY = ".staging."
EXPECTED_VERISON_CHARS = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.']


class Version:
    def __init__(self, *args):
        self._identifiers = args
        self.staging = False

    @classmethod
    def default(cls):
        return Version(0)

    @classmethod
    def parse(cls, version: str):
        staging_version = None
        if STAGING_KEY in version:
            index = version.find(STAGING_KEY)
            staging_version = int(version[index + len(STAGING_KEY):])
            version = version[0:index]
        version = Version._removeUnexpected(version)
        parts = []
        for part in version.split("."):
            if len(part) > 0:
                parts.append(int(part))
        if staging_version is not None:
            parts.append(staging_version)
        if len(parts) == 0:
            parts.append(0)
        ret = Version(*parts)
        if staging_version is not None:
            ret.staging = True
        return ret

    @classmethod
    def _removeUnexpected(cls, version: str):
        ret = ""
        for c in version:
            if c in EXPECTED_VERISON_CHARS:
                ret += c
        while ".." in ret:
            ret = ret.replace("..", ".")
        return ret

    def __getitem__(self, key):
        return self._identifiers[key]

    def length(self):
        return len(self._identifiers)

    def _compare(self, other):
        i = 0
        while(i < min(self.length(), other.length())):
            if self[i] < other[i]:
                return -1
            if self[i] > other[i]:
                return 1
            i += 1
        if self.length() < other.length():
            return -1
        if self.length() > other.length():
            return 1
        return 0

    def __lt__(self, other):
        return self._compare(other) < 0

    def __le__(self, other):
        return self._compare(other) <= 0

    def __eq__(self, other):
        return self._compare(other) == 0

    def __ne__(self, other):
        return self._compare(other) != 0

    def __gt__(self, other):
        return self._compare(other) > 0

    def __ge__(self, other):
        return self._compare(other) >= 0

    def __str__(self):
        return ".".join(str(i) for i in self._identifiers)
