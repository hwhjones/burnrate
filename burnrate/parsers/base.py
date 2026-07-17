import os
import stat
from abc import ABC, abstractmethod
from datetime import date as calendar_date, datetime
from pathlib import Path
from typing import Optional


SKIP_CATEGORIES = (
    "malformed_json",
    "non_object_json",
    "invalid_record_shape",
    "unusable_usage_record",
)


def invalid_optional_identity(value) -> bool:
    """Return whether a supplied optional identity is not a string."""
    return value is not None and not isinstance(value, str)


def optional_identity(value) -> Optional[str]:
    """Return a non-empty string identity, or None for a missing value."""
    return value if isinstance(value, str) and value else None


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
        """Clear record and file diagnostics for a new scan."""
        self.skip_counts = {category: 0 for category in SKIP_CATEGORIES}
        self.rejected_usage_records = 0
        self.invalid_input_path = False
        self.file_read_errors = []
        self.totals_potentially_incomplete = False
        self.scan_incomplete = False

    @staticmethod
    def _error_detail(error: Exception) -> str:
        """Return a concise, stable description for a filesystem error."""
        if isinstance(error, UnicodeError):
            return "invalid UTF-8"
        if isinstance(error, FileNotFoundError):
            return "not found"
        if isinstance(error, OSError) and error.strerror:
            return str(error.strerror)
        return str(error).strip() or error.__class__.__name__

    def _record_input_path_error(
        self,
        provider: str,
        path: Path,
        error: Exception,
    ) -> None:
        """Record a top-level path that could not be inspected."""
        detail = self._error_detail(error)
        self.invalid_input_path = True
        print(f"[{provider}] Could not inspect {path}: {detail}")

    def _record_discovery_error(
        self,
        provider: str,
        path: Path,
        error: OSError,
    ) -> None:
        """Record a directory that could not be enumerated."""
        detail = self._error_detail(error)
        self.scan_incomplete = True
        print(f"[{provider}] Could not scan {path}: {detail}")

    def _discover_jsonl_files(
        self,
        provider: str,
        path: Path,
    ) -> Optional[list[Path]]:
        """Return deterministic JSONL inputs while reporting discovery errors."""
        try:
            mode = path.stat().st_mode
        except OSError as error:
            self._record_input_path_error(provider, path, error)
            return None

        if stat.S_ISREG(mode):
            return [path]
        if not stat.S_ISDIR(mode):
            self._record_input_path_error(
                provider,
                path,
                OSError("not a file or directory"),
            )
            return None

        files = []

        def onerror(error: OSError) -> None:
            failed_path = Path(error.filename) if error.filename else path
            self._record_discovery_error(provider, failed_path, error)

        try:
            for directory, dirnames, filenames in os.walk(
                path,
                topdown=True,
                onerror=onerror,
                followlinks=False,
            ):
                dirnames.sort()
                for filename in sorted(filenames):
                    if Path(filename).match("*.jsonl"):
                        files.append(Path(directory) / filename)
        except OSError as error:
            onerror(error)

        return sorted(files)

    def _record_skip(self, category: str, *, usage_like: bool = False) -> None:
        """Record why an input record was rejected."""
        self.skip_counts[category] += 1
        if usage_like:
            self.rejected_usage_records += 1
            self.totals_potentially_incomplete = True

    def _record_file_error(
        self,
        provider: str,
        file_path,
        error: Exception,
    ) -> None:
        """Record and report a file that could not be read completely."""
        detail = self._error_detail(error)
        self.file_read_errors.append(
            {
                "filepath": str(file_path),
                "error": error.__class__.__name__,
                "message": detail,
            }
        )
        self.scan_incomplete = True
        print(f"[{provider}] Could not read {file_path}: {detail}")

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
