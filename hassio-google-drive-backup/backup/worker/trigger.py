from ..logger import getLogger

logger = getLogger(__name__)


class Trigger():
    def __init__(self):
        self._triggered = False

    def trigger(self) -> None:
        self._triggered = True

    def reset(self) -> None:
        self._triggered = False

    def triggered(self) -> bool:
        return self._triggered

    def name(self):
        return "Unnamed Trigger"

    def check(self) -> bool:
        if self.triggered():
            self.reset()
            return True
        return False
