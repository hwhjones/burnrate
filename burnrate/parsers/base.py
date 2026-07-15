from abc import ABC, abstractmethod
from datetime import date as calendar_date, datetime
from typing import Optional


SKIP_CATEGORIES = (
    "malformed_json",
    "non_object_json",
    "invalid_record_shape",
    "unusable_usage_record",
)


def parse_timestamp_date(timestamp) -> Optional[calendar_date]:
    """Return the calendar date for a valid ISO timestamp, otherwise None."""
    if not isinstance(timestamp, str) or not timestamp.strip():
        return None

    normalized = timestamp.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"

    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return None


class BaseParser(ABC):
    """Abstract base parser defining the public contract for all log parsers.

    Concrete implementations must provide methods to parse log data and
    generate a summary report.
    """

    def _reset_diagnostics(self) -> None:
        """Clear record-rejection diagnostics for a new scan."""
        self.skip_counts = {category: 0 for category in SKIP_CATEGORIES}
        self.rejected_usage_records = 0

    def _record_skip(self, category: str, *, usage_like: bool = False) -> None:
        """Record why an input record was rejected."""
        self.skip_counts[category] += 1
        if usage_like:
            self.rejected_usage_records += 1

    @property
    def totals_potentially_incomplete(self) -> bool:
        """Whether recognizable usage records were rejected by the scan."""
        return self.rejected_usage_records > 0

    def _print_diagnostics(self, provider: str) -> None:
        """Print a compact summary when the scan rejected any records."""
        if not any(self.skip_counts.values()):
            return

        labels = {
            "malformed_json": "malformed JSON",
            "non_object_json": "non-object JSON",
            "invalid_record_shape": "invalid shape",
            "unusable_usage_record": "unusable usage",
        }
        counts = ", ".join(
            f"{labels[category]}={self.skip_counts[category]}"
            for category in SKIP_CATEGORIES
            if self.skip_counts[category]
        )
        print(f"[{provider}] Skipped records: {counts}")
        if self.totals_potentially_incomplete:
            print(
                f"[{provider}] Warning: totals may be incomplete; "
                f"{self.rejected_usage_records} usage-like record(s) were rejected."
            )

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
