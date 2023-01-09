from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime


class Precache(ABC):
    @abstractmethod
    def cached(self, source: str, date: datetime) -> Any:
        """For a given source and datetime, returns valid precached results if they're available"""
        pass

    @abstractmethod
    def clear(self):
        """Clears any cached results stored"""
        pass