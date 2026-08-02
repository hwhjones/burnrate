"""Deterministic normalization for privacy-bounded trace events."""

import hashlib
import json
import re
from copy import deepcopy


_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_HEX_ID = re.compile(r"\b[0-9a-f]{16,}\b", re.IGNORECASE)
_ISO_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?",
    re.IGNORECASE,
)
_WINDOWS_HOME = re.compile(r"^[a-z]:/users/[^/]+", re.IGNORECASE)
_POSIX_HOME = re.compile(r"^/home/[^/]+")


class CodexTraceNormalizer:
    """Add deterministic, inspectable evidence signatures to trace events.

    Raw structured evidence is copied unchanged.  Normalized identities are
    allocated in first-seen order, so values that change between sessions do
    not change a signature while session and agent relationships remain clear.
    """

    def __init__(self) -> None:
        self._sessions = {}
        self._agents = {}

    def normalize(self, events: list[dict]) -> list[dict]:
        """Return copies of ``events`` annotated with normalized evidence."""
        return [self.normalize_event(event) for event in events]

    def normalize_event(self, event: dict) -> dict:
        """Copy one event and add its classification and evidence signature."""
        result = deepcopy(event)
        normalized = {
            "session_id": self._identity("session", event.get("session_id")),
            "agent_id": self._identity("agent", event.get("agent_id")),
            "parent_agent_id": self._identity(
                "agent", event.get("parent_agent_id")
            ),
            "timestamp": "<timestamp>" if isinstance(event.get("timestamp"), str) else None,
            "command": normalize_command(event.get("command")),
            "path": normalize_path(event.get("path")),
            "read_path": normalize_path(event.get("read_path") or extract_read_path(event.get("command"))),
            "exit_status": normalize_exit_status(event.get("exit_status")),
            "error_text": normalize_error_text(event.get("error_text")),
            "error_evidence": _normal_string(event.get("error_evidence")),
            "mutation_status": _normal_string(event.get("mutation_status")),
        }
        normalized = {key: value for key, value in normalized.items() if value is not None}
        operation = classify_operation(event, normalized)
        signature_fields = {
            "event_type": event.get("event_type", "unknown"),
            "operation": operation,
            **normalized,
        }
        canonical = json.dumps(signature_fields, sort_keys=True, separators=(",", ":"))
        result["operation"] = operation
        result["normalized"] = normalized
        result["evidence_signature"] = {
            "version": "codex-trace-v1",
            "fields": signature_fields,
            "value": "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
        return result

    def _identity(self, kind: str, value):
        if not isinstance(value, str) or not value:
            return None
        mapping = self._sessions if kind == "session" else self._agents
        if value not in mapping:
            mapping[value] = f"{kind}-{len(mapping) + 1}"
        return mapping[value]


def normalize_events(events: list[dict]) -> list[dict]:
    """Normalize a timeline with stable first-seen session and agent aliases."""
    return CodexTraceNormalizer().normalize(events)


def normalize_command(value):
    """Collapse formatting and replace volatile IDs and embedded timestamps."""
    if not isinstance(value, str) or not value.strip():
        return None
    return _normalize_volatile_text(" ".join(value.strip().split()))


def normalize_path(value):
    """Normalize separators, home prefixes, and volatile path components."""
    if isinstance(value, list):
        paths = [normalize_path(item) for item in value]
        return [item for item in paths if item is not None] or None
    if not isinstance(value, str) or not value.strip():
        return None
    path = value.strip().replace("\\", "/")
    path = re.sub(r"/+", "/", path)
    path = _WINDOWS_HOME.sub("<home>", path)
    path = _POSIX_HOME.sub("<home>", path)
    return _normalize_volatile_text(path.rstrip("/"))


def extract_read_path(command):
    """Extract only explicit file targets from conservative read commands."""
    if not isinstance(command, str):
        return None
    match = re.search(
        r"(?i)\b(?:get-content|gc)\b.*?-(?:literal)?path\s+(['\"])(.*?)\1",
        command,
    )
    if match is not None:
        return match.group(2)
    match = re.search(r"(?i)\b(?:cat|type)\s+(['\"])(.*?)\1", command)
    return match.group(2) if match is not None else None

def normalize_exit_status(value):
    """Represent numeric statuses consistently without coercing malformed data."""
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return "success" if value == 0 else f"failure:{value}"


def normalize_error_text(value):
    """Normalize structured error text while masking volatile fragments."""
    if not isinstance(value, str) or not value.strip():
        return None
    return _normalize_volatile_text(" ".join(value.strip().lower().split()))


def classify_operation(event: dict, normalized: dict) -> str:
    """Classify structured activity using explicit command-token rules."""
    if event.get("event_type") == "patch" or normalized.get("mutation_status"):
        return "mutation"
    command = normalized.get("command", "").lower()
    tool_name = _normal_string(event.get("tool_name")) or ""
    if tool_name in {"apply_patch", "write_file"} or _command_matches(command, r"apply_patch\b"):
        return "mutation"
    if _command_matches(command, r"(?:git|gh)\b"):
        return "version-control"
    if _command_matches(command, r"(?:login|logout|whoami)\b") or re.search(r"\bauth\b", command):
        return "authentication"
    if _command_matches(command, r"(?:pytest|unittest)\b") or re.search(r"\b(?:cargo|go|npm)\s+test\b", command):
        return "test"
    if _command_matches(command, r"(?:rg\s+--files|find\b|get-childitem\b|dir\b|ls\b)"):
        return "discovery"
    if _command_matches(command, r"(?:get-content\b|cat\b|type\b|head\b|tail\b|rg\b)"):
        return "read"
    return "unknown"

def _normal_string(value):
    return value if isinstance(value, str) and value else None


def _normalize_volatile_text(value: str) -> str:
    value = _UUID.sub("<uuid>", value)
    value = _HEX_ID.sub("<hex-id>", value)
    return _ISO_TIMESTAMP.sub("<timestamp>", value)


def _command_matches(command: str, pattern: str) -> bool:
    """Match a command token or argument without matching inside a word."""
    return bool(re.search(r"(?<![a-z0-9_-])" + pattern, command))
