"""Thin, privacy-safe reader for the Codex pattern scan.

This module intentionally extracts only facts needed by the first three
direct observation rules. It is not a general Codex event model.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_READ_TYPES = {"read", "read_file", "file_read", "open_file"}
_MUTATION_TYPES = {"mutation", "patch", "file_write", "write_file", "patch_apply_end"}
_READ_COMMAND_RE = re.compile(r"(?:Get-Content|cat|type|head|tail|sed)(?:\s|$)", re.I)
_TEST_RE = re.compile(r"(?:^|\s)(?:pytest|py\.test|unittest|npm\s+test|cargo\s+test|go\s+test)(?:\s|$)", re.I)
_MUTATION_RE = re.compile(r"(?:apply_patch|git\s+(?:apply|commit)|(?:set|add|out)-content|touch\s|mkdir\s|npm\s+install)", re.I)
RULE_CATALOG = {
    "R-READ-01": {"name": "Repeated file reads", "classification": "observation", "explanation": "The same normalized file was read more than once.", "try_next_experiment": "Reference the earlier read when it remains current."},
    "R-RETRY-01": {"name": "Ineffective retries", "classification": "observation", "explanation": "The same failed command and failure fingerprint recurred consecutively.", "try_next_experiment": "Change the command or inspect the failure before retrying it."},
    "R-TEST-01": {"name": "Test churn", "classification": "observation", "explanation": "The same test command recurred without an observed successful mutation.", "try_next_experiment": "Make or verify the smallest mutation before rerunning the same test."},
}


class PatternFact:
    """One normalized fact required by a direct observation rule."""

    def __init__(self, session_id: str, sequence: int, filepath: str, line: int,
                 timestamp: str | None = None, kind: str = "unknown",
                 target: str | None = None, command: str | None = None,
                 failure_fingerprint: str | None = None,
                 successful_mutation: bool = False) -> None:
        self.session_id = session_id
        self.sequence = sequence
        self.filepath = filepath
        self.line = line
        self.timestamp = timestamp
        self.kind = kind
        self.target = target
        self.command = command
        self.failure_fingerprint = failure_fingerprint
        self.successful_mutation = successful_mutation


class SessionFacts:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.first_timestamp: str | None = None
        self.last_timestamp: str | None = None
        self.facts: list[PatternFact] = []
        self.final_token_usage: dict[str, dict[str, Any]] = {}


class PatternScan:
    def __init__(self, status: str) -> None:
        self.status = status
        self.sessions: list[SessionFacts] = []
        self.files_scanned = 0
        self.malformed_records = 0
        self.file_errors: list[dict[str, str]] = []


class PatternReader:
    """Read Codex JSONL logs into the minimum PR1 session facts."""

    def __init__(self, log_path: str = "~/.codex/sessions/") -> None:
        self.log_path = Path(log_path).expanduser()

    def scan(self) -> PatternScan:
        files, invalid = self._discover()
        if invalid:
            return PatternScan(status="invalid")

        sessions: dict[str, SessionFacts] = {}
        result = PatternScan(status="complete")

        for path in files:
            result.files_scanned += 1
            try:
                self._read_file(path, sessions, result)
            except (OSError, UnicodeError) as error:
                result.file_errors.append({
                    "filepath": str(path),
                    "error": error.__class__.__name__,
                })

        if result.file_errors:
            result.status = "partial" if sessions else "invalid"
        elif not files:
            result.status = "empty"

        for session in sessions.values():
            session.facts.sort(key=lambda fact: fact.sequence)
        result.sessions = sorted(sessions.values(), key=lambda session: session.session_id)
        return result

    def _discover(self) -> tuple[list[Path], bool]:
        try:
            mode = self.log_path.stat().st_mode
        except OSError:
            return [], True
        if stat.S_ISREG(mode):
            return [self.log_path], False
        if not stat.S_ISDIR(mode):
            return [], True

        files: list[Path] = []
        try:
            for directory, dirnames, filenames in os.walk(self.log_path, followlinks=False):
                dirnames.sort()
                files.extend(Path(directory) / name for name in sorted(filenames) if name.endswith(".jsonl"))
        except OSError:
            return sorted(files), True
        return sorted(files), False

    def _read_file(self, path: Path, sessions: dict[str, SessionFacts], result: PatternScan) -> None:
        resolved = str(path.resolve())
        sequence = 0
        pending_calls: dict[str, PatternFact] = {}
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    result.malformed_records += 1
                    continue
                if not isinstance(record, dict):
                    result.malformed_records += 1
                    continue

                payload = record.get("payload")
                if not isinstance(payload, dict):
                    payload = {}
                session_id = _string(record.get("session_id")) or _string(payload.get("session_id")) or resolved
                session = sessions.setdefault(session_id, SessionFacts(session_id=session_id))
                timestamp = _timestamp(record.get("timestamp"))
                if timestamp is not None:
                    session.first_timestamp = min(filter(None, [session.first_timestamp, timestamp]), default=timestamp)
                    session.last_timestamp = max(filter(None, [session.last_timestamp, timestamp]), default=timestamp)

                if payload.get("type") == "token_count":
                    self._retain_token_snapshot(record, payload, session, resolved, line_number, timestamp)

                if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                    call_id = _string(payload.get("call_id"))
                    if call_id and call_id in pending_calls:
                        _apply_call_output(pending_calls[call_id], payload.get("output"))
                    continue

                fact = _fact_from_record(record, payload, session_id, sequence, resolved, line_number, timestamp)
                if fact is not None:
                    session.facts.append(fact)
                    sequence += 1
                    call_id = _string(payload.get("call_id"))
                    if call_id and payload.get("type") in ("function_call", "custom_tool_call"):
                        pending_calls[call_id] = fact

    @staticmethod
    def _retain_token_snapshot(record: dict[str, Any], payload: dict[str, Any], session: SessionFacts,
                               filepath: str, line: int, timestamp: str | None) -> None:
        info = payload.get("info")
        usage = info.get("last_token_usage") if isinstance(info, dict) else None
        if not isinstance(usage, dict):
            return
        request_id = _string(record.get("requestId")) or f"{filepath}:{line}"
        candidate = {"timestamp": timestamp, "source": {"filepath": filepath, "line": line}, "usage": _safe_usage(usage)}
        current = session.final_token_usage.get(request_id)
        if current is None or (candidate["timestamp"] or "") >= (current["timestamp"] or ""):
            session.final_token_usage[request_id] = candidate


def _fact_from_record(record: dict[str, Any], payload: dict[str, Any], session_id: str,
                      sequence: int, filepath: str, line: int, timestamp: str | None) -> PatternFact | None:
    event_type = _string(payload.get("type")) or _string(record.get("type"))
    name = _string(payload.get("name")) or _string(payload.get("tool_name"))
    command = _normalize_command(payload.get("command") or payload.get("cmd"))
    target = _normalize_target(payload.get("path") or payload.get("filepath"))
    if event_type in ("function_call", "custom_tool_call"):
        arguments = _decode_arguments(payload.get("arguments") or payload.get("input"))
        if isinstance(arguments, dict):
            command = _normalize_command(arguments.get("command") or arguments.get("cmd")) or command
            target = _normalize_target(arguments.get("path") or arguments.get("filepath")) or target
        if name == "apply_patch":
            event_type = "mutation"
    if command and target is None:
        target = _target_from_command(command)
    kind = "unknown"
    if (target and command and _READ_COMMAND_RE.search(command)) or event_type in _READ_TYPES or name in _READ_TYPES:
        kind = "read"
    elif event_type in _MUTATION_TYPES or name in _MUTATION_TYPES:
        kind = "mutation"
    elif command and _TEST_RE.search(command):
        kind = "test"
    elif command:
        kind = "command"
    else:
        return None

    successful_mutation = bool(payload.get("success") is True or payload.get("exit_code") == 0) and (
        kind == "mutation" or bool(command and _MUTATION_RE.search(command))
    )
    failure = payload.get("failure_fingerprint") or payload.get("error")
    exit_code = payload.get("exit_code")
    if failure is None and isinstance(exit_code, int) and exit_code != 0:
        failure = f"exit_code:{exit_code}"
    failure_fingerprint = _normalize_text(failure) if failure is not None else None
    return PatternFact(session_id, sequence, filepath, line, timestamp, kind, target, command,
                       failure_fingerprint, successful_mutation)


def _safe_usage(usage: dict[str, Any]) -> dict[str, int]:
    return {key: value for key, value in usage.items() if key.endswith("_tokens") and isinstance(value, int) and not isinstance(value, bool)}


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _normalize_text(value: Any) -> str | None:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) and value.strip() else None


def _normalize_command(value: Any) -> str | None:
    return _normalize_text(value)


def _normalize_target(value: Any) -> str | None:
    value = _string(value)
    if not value or value.startswith("$") or "${" in value:
        return None
    return value.replace("\\", "/")


def detect_observations(scan: PatternScan) -> list[dict[str, Any]]:
    """Detect the three direct observations from a PatternScan."""
    occurrences = []
    for session in scan.sessions:
        occurrences.extend(_detect_repeated_reads(session))
        occurrences.extend(_detect_retries(session))
        occurrences.extend(_detect_test_churn(session))
    results = []
    for rule_id in RULE_CATALOG:
        rule_occurrences = [item for item in occurrences if item["rule_id"] == rule_id]
        if not rule_occurrences:
            continue
        metadata = RULE_CATALOG[rule_id]
        results.append({
            "id": rule_id,
            "name": metadata["name"],
            "classification": metadata["classification"],
            "count": len(rule_occurrences),
            "affected_sessions": len({item["session_id"] for item in rule_occurrences}),
            "explanation": metadata["explanation"],
            "try_next_experiment": metadata["try_next_experiment"],
            "examples": [item["example"] for item in rule_occurrences[:3]],
        })
    return sorted(results, key=lambda result: (-result["count"], result["id"]))


def _detect_repeated_reads(session: SessionFacts) -> list[dict[str, Any]]:
    by_target: dict[str, list[PatternFact]] = {}
    for fact in session.facts:
        if fact.kind == "read" and fact.target:
            by_target.setdefault(fact.target, []).append(fact)
    occurrences = []
    for target in sorted(by_target):
        for fact in by_target[target][1:]:
            occurrences.append(_occurrence("R-READ-01", session.session_id, fact, target=target))
    return occurrences


def _detect_retries(session: SessionFacts) -> list[dict[str, Any]]:
    occurrences = []
    previous_key = None
    for fact in session.facts:
        if fact.kind == "test":
            previous_key = None
            continue
        if fact.kind != "command" or not fact.command:
            continue
        if not fact.failure_fingerprint:
            previous_key = None
            continue
        key = (fact.command, fact.failure_fingerprint)
        if key == previous_key:
            occurrences.append(_occurrence("R-RETRY-01", session.session_id, fact, command=fact.command))
        previous_key = key
    return occurrences


def _detect_test_churn(session: SessionFacts) -> list[dict[str, Any]]:
    occurrences = []
    previous_command = None
    for fact in session.facts:
        if fact.successful_mutation:
            previous_command = None
            continue
        if fact.kind != "test" or not fact.command:
            continue
        if fact.command == previous_command:
            occurrences.append(_occurrence("R-TEST-01", session.session_id, fact, command=fact.command))
        previous_command = fact.command
    return occurrences


def _occurrence(rule_id: str, session_id: str, fact: PatternFact, **fields: str) -> dict[str, Any]:
    example = {"filepath": fact.filepath, "line": fact.line}
    example.update(fields)
    return {"rule_id": rule_id, "session_id": session_id, "sequence": fact.sequence, "example": example}

def _decode_arguments(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _target_from_command(command: str) -> str | None:
    quoted = re.search(r"(?:Get-Content|cat|type|head|tail|sed)\s+(?:-LiteralPath\s+)?['\"]([^'\"]+)['\"]", command, re.I)
    if quoted:
        return _normalize_target(quoted.group(1))
    unquoted = re.search(r"(?:Get-Content|cat|type|head|tail|sed)\s+(?:-LiteralPath\s+)?([^\s|;]+)", command, re.I)
    return _normalize_target(unquoted.group(1)) if unquoted else None

def _output_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_output_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_output_text(item) for item in value.values())
    return ""


def _apply_call_output(fact: PatternFact, output: Any) -> None:
    text = _output_text(output)
    match = re.search(r"(?:exit\s+code|exit_code|status)\s*[:=]\s*(-?\d+)", text, re.I)
    if match:
        exit_code = int(match.group(1))
        if exit_code == 0:
            fact.failure_fingerprint = None
            if fact.kind == "mutation" or (fact.command and _MUTATION_RE.search(fact.command)):
                fact.successful_mutation = True
        else:
            fact.failure_fingerprint = f"exit_code:{exit_code}"
    elif text and re.search(r"\b(?:failed|error)\b", text, re.I):
        fact.failure_fingerprint = "output:" + hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]