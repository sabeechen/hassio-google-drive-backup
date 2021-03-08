from typing import List, TypeVar, Generic, Mapping

T = TypeVar('T')
K = TypeVar('K')


class RangeLookup(Generic[T, K]):
    def __init__(self, source: List[T], mapping: Mapping[T, K]):
        self.source = source
        self.map = mapping

    def matches(self, start: K, end: K):
        range_start = self._searchFirstGreaterOrEqual(start)
        range_end = self._searchLastLessOrEqual(end)

        x = range_start
        while (x <= range_end):
            if x >= 0 and x < len(self.source):
                yield self.source[x]
            x += 1

    def matchList(self, start, end):
        ret = []
        for x in self.matches(start, end):
            ret.append(x)
        return ret

    def _searchFirstGreaterOrEqual(self, val):
        first = 0
        last = len(self.source) - 1
        if self.map(self.source[last]) < val:
            return last + 1
        while first != last:
            mid = int((first + last) / 2)
            if self.map(self.source[mid]) < val:
                first = mid + 1
            else:
                last = mid
        return first

    def _searchLastLessOrEqual(self, val):
        first = 0
        last = len(self.source) - 1
        if self.map(self.source[0]) > val:
            return -1
        while first != last:
            mid = int((first + last) / 2)
            if self.map(self.source[mid]) > val:
                last = mid - 1
            elif first != mid:
                first = mid
            elif self.map(self.source[last]) <= val:
                return last
            else:
                return first
        return first
