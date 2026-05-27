from abc import ABC, abstractmethod

class BaseParser(ABC):
    @abstractmethod
    def parse(self):
        """Must return a list of runs."""
        pass

    @abstractmethod
    def summary(self):
        """Must print a standard summary."""
        pass