from abc import ABC, abstractmethod

class BaseParser(ABC):
    """Abstract base parser defining the public contract for all log parsers.

    Concrete implementations must provide methods to parse log data and
    generate a summary report.
    """

    @abstractmethod
    def parse(self):
        """Parse logs from the configured input path.

        This method should process log files, extract relevant usage data,
        and populate the parser's internal state (e.g., `self.runs`,
        `self.total_tokens`, `self.total_cost`). It should return a list
        of individual parsed run records.
        """
        pass

    @abstractmethod
    def summary(self):
        """Print a summary report after parsing is complete."""
        pass