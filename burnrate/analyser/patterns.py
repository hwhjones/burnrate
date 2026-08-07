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
_TEST_MODULE_RE = re.compile(r"\b(?:python(?:3)?|py)\s+-m\s+(pytest|unittest)\b", re.I)
_MUTATION_RE = re.compile(r"(?:apply_patch|git\s+(?:apply|commit)|(?:set|add|out)-content|touch\s|mkdir\s|npm\s+install)", re.I)
EXPLORATION_CALL_THRESHOLD = 4
SESSION_DURATION_SECONDS_THRESHOLD = 35 * 60
SESSION_WORK_TOKEN_THRESHOLD = 50_000
LARGE_OUTPUT_CHAR_THRESHOLD = 8_000
SUBAGENT_SPAWN_THRESHOLD = 6
RULE_CATALOG = {
    "R-READ-01": {"name": "Repeated file reads", "classification": "observation", "explanation": "The same normalized file was read more than once.", "try_next_experiment": "Reference the earlier read when it remains current."},
    "R-RETRY-01": {"name": "Ineffective retries", "classification": "observation", "explanation": "The same failed command and failure fingerprint recurred consecutively.", "try_next_experiment": "Change the command or inspect the failure before retrying it."},
    "R-TEST-01": {"name": "Test churn", "classification": "observation", "explanation": "The same test command recurred without an observed successful mutation.", "try_next_experiment": "Make or verify the smallest mutation before rerunning the same test."},
    "R-EXP-01": {"name": "Exploration pile-up", "classification": "frequency_signal", "threshold": EXPLORATION_CALL_THRESHOLD, "count_scope": "turn_occurrences", "explanation": "At least four read or discovery calls occurred in one turn.", "try_next_experiment": "Review the observed exploration sequence and choose the next step."},
    "R-SESSION-01": {"name": "Long session", "classification": "frequency_signal", "threshold": SESSION_DURATION_SECONDS_THRESHOLD, "count_scope": "affected_sessions", "explanation": "The observed session duration reached 35 minutes.", "try_next_experiment": "Review the session timeline and decide whether to continue."},
    "R-TOKEN-01": {"name": "Token pile-up", "classification": "frequency_signal", "threshold": SESSION_WORK_TOKEN_THRESHOLD, "count_scope": "affected_sessions", "explanation": "Observed session work tokens reached 50,000.", "try_next_experiment": "Review the session token usage alongside its work."},
    "R-OUT-01": {"name": "Large tool output", "classification": "frequency_signal", "threshold": LARGE_OUTPUT_CHAR_THRESHOLD, "count_scope": "direct_occurrences", "explanation": "One observed tool result reached 8,000 characters.", "try_next_experiment": "Review the source reference for the large tool result."},
    "R-SUBAGENT-01": {"name": "Subagent-heavy session", "classification": "frequency_signal", "threshold": SUBAGENT_SPAWN_THRESHOLD, "count_scope": "affected_sessions", "explanation": "At least six lineage-backed subagent spawns occurred in one session.", "try_next_experiment": "Review the observed subagent lineage and session context."},
    "R-WEB-01": {"name": "Web-heavy session", "classification": "frequency_signal", "count_scope": "direct_occurrences", "explanation": "Observed web search or fetch calls occurred in the session.", "try_next_experiment": "Review the observed web call sequence and its context."},
}


class PatternFact:
    """One normalized fact required by a direct observation rule."""

    def __init__(self, session_id: str, sequence: int, filepath: str, line: int,
                 timestamp: str | None = None, kind: str = "unknown",
                 target: str | None = None, command: str | None = None,
                 failure_fingerprint: str | None = None,
                 successful_mutation: bool = False, turn_id: str | None = None,
                 output_chars: int | None = None, web_call: bool = False,
                 subagent_spawn: bool = False) -> None:
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
        self.turn_id = turn_id
        self.output_chars = output_chars
        self.web_call = web_call
        self.subagent_spawn = subagent_spawn


class SessionFacts:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.first_timestamp: str | None = None
        self.last_timestamp: str | None = None
        self.has_missing_timestamp = False
        self.facts: list[PatternFact] = []
        self.final_token_usage: dict[str, dict[str, Any]] = {}


class PatternScan:
    def __init__(self, status: str) -> None:
        self.status = status
        self.sessions: list[SessionFacts] = []
        self.files_scanned = 0
        self.malformed_records = 0
        self.file_errors: list[dict[str, str]] = []
        self.diagnostics: dict[str, int] = {"retry_candidates_suppressed": 0}


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
        pending_calls: dict[tuple[str, str], PatternFact] = {}
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
                if timestamp is None:
                    session.has_missing_timestamp = True
                if timestamp is not None:
                    session.first_timestamp = min(filter(None, [session.first_timestamp, timestamp]), default=timestamp)
                    session.last_timestamp = max(filter(None, [session.last_timestamp, timestamp]), default=timestamp)

                if payload.get("type") == "token_count":
                    self._retain_token_snapshot(record, payload, session, resolved, line_number, timestamp)

                if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                    call_id = _string(payload.get("call_id"))
                    if call_id and (session_id, call_id) in pending_calls:
                        _apply_call_output(pending_calls[(session_id, call_id)], payload.get("output"))
                    continue

                fact = _fact_from_record(record, payload, session_id, sequence, resolved, line_number, timestamp)
                if fact is not None:
                    session.facts.append(fact)
                    sequence += 1
                    call_id = _string(payload.get("call_id"))
                    if call_id and payload.get("type") in ("function_call", "custom_tool_call"):
                        pending_calls[(session_id, call_id)] = fact

    @staticmethod
    def _retain_token_snapshot(record: dict[str, Any], payload: dict[str, Any], session: SessionFacts,
                               filepath: str, line: int, timestamp: str | None) -> None:
        info = payload.get("info")
        usage = info.get("last_token_usage") if isinstance(info, dict) else None
        if not isinstance(usage, dict):
            return
        request_id = (_string(record.get("requestId")) or
                      _string(payload.get("requestId")) or f"{filepath}:{line}")
        candidate = {"timestamp": timestamp, "source": {"filepath": filepath, "line": line}, "usage": _safe_usage(usage)}
        current = session.final_token_usage.get(request_id)
        if current is None or (candidate["timestamp"] or "") >= (current["timestamp"] or ""):
            session.final_token_usage[request_id] = candidate


def _fact_from_record(record: dict[str, Any], payload: dict[str, Any], session_id: str,
                      sequence: int, filepath: str, line: int, timestamp: str | None) -> PatternFact | None:
    event_type = _string(payload.get("type")) or _string(record.get("type"))
    name = _string(payload.get("name")) or _string(payload.get("tool_name"))
    command = _normalize_command(payload.get("command") or payload.get("cmd") or payload.get("test_command"))
    target = _normalize_target(payload.get("path") or payload.get("filepath"))
    if event_type in ("function_call", "custom_tool_call"):
        arguments = _decode_arguments(payload.get("arguments") or payload.get("input"))
        if isinstance(arguments, dict):
            command = _normalize_command(arguments.get("command") or arguments.get("cmd") or arguments.get("test_command")) or command
            target = _normalize_target(arguments.get("path") or arguments.get("filepath")) or target
            if arguments.get("is_test") is True and command and not _TEST_RE.search(command):
                command = "pytest " + command
        if name == "apply_patch":
            event_type = "mutation"
    if command and target is None:
        target = _target_from_command(command)
    kind = "unknown"
    if (target and command and _READ_COMMAND_RE.search(command)) or event_type in _READ_TYPES or name in _READ_TYPES:
        kind = "read"
    elif event_type in _MUTATION_TYPES or name in _MUTATION_TYPES:
        kind = "mutation"
    elif command and (_TEST_RE.search(command) or _TEST_MODULE_RE.search(command)):
        kind = "test"
    elif command:
        kind = "command"
    elif event_type in ("function_call", "custom_tool_call") or (event_type and re.search(r"\b(?:web_search|web_fetch|browser_search|browser_fetch|spawn_subagent|spawn_agent|subagent_spawn)\b", event_type, re.I)):
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
    turn_id = _telemetry_string(record, payload, "turn_id", "turnId", "turn")
    lineage = _telemetry_value(record, payload, "lineage", "parent_session_id", "parent_call_id", "parentCallId")
    web_call = _is_web_call(event_type, name, payload, record)
    subagent_spawn = _is_subagent_spawn(event_type, name, payload, record) and bool(lineage)
    output_chars = _output_length(_telemetry_value(record, payload, "output", "result"))
    return PatternFact(session_id, sequence, filepath, line, timestamp, kind, target, command,
                       failure_fingerprint, successful_mutation, turn_id, output_chars, web_call, subagent_spawn)


def _usage_total(usage: dict[str, int]) -> int:
    if 'total_tokens' in usage:
        return usage['total_tokens']
    return sum(usage.values())


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
    value = _normalize_text(value)
    if not value:
        return None
    value = re.sub(r"^&\s+", "", value)
    value = re.sub(r"\b(?:python(?:3)?|py)\s+-m\s+pytest\b", "pytest", value, flags=re.I)
    value = re.sub(r"\b(?:python(?:3)?|py)\s+-m\s+unittest\b", "unittest", value, flags=re.I)
    return value


def _normalize_target(value: Any) -> str | None:
    value = _string(value)
    if not value or value.startswith("$") or "${" in value:
        return None
    return value.replace("\\", "/")




def _telemetry_value(record: dict[str, Any], payload: dict[str, Any], *keys: str) -> Any:
    for source in (payload, record):
        for key in keys:
            if source.get(key) is not None:
                return source[key]
    return None

def _telemetry_string(record: dict[str, Any], payload: dict[str, Any], *keys: str) -> str | None:
    value = _telemetry_value(record, payload, *keys)
    return _normalize_text(value) if isinstance(value, str) else None

def _output_length(value: Any) -> int | None:
    return None if value is None else len(_output_text(value))

def _is_discovery(fact: PatternFact) -> bool:
    return bool(fact.command and re.search(r"\b(?:find|dir|ls|tree|rg|ripgrep|search)\b", fact.command, re.I))

def _is_web_call(event_type: str | None, name: str | None, payload: dict[str, Any], record: dict[str, Any]) -> bool:
    if _telemetry_value(record, payload, "web_call", "web", "is_web") is True:
        return True
    text = " ".join(filter(None, (event_type, name, _string(payload.get("tool_name")))))
    return bool(re.search(r"\b(?:web_search|web_fetch|web\.run|browser_search|browser_fetch)\b", text, re.I))

def _is_subagent_spawn(event_type: str | None, name: str | None, payload: dict[str, Any], record: dict[str, Any]) -> bool:
    if _telemetry_value(record, payload, "subagent_spawn", "spawned_subagent", "is_subagent_spawn") is True:
        return True
    text = " ".join(filter(None, (event_type, name, _string(payload.get("tool_name")))))
    return bool(re.search(r"\b(?:spawn_subagent|spawn_agent|subagent_spawn|subagent)\b", text, re.I))

def _detect_frequency_signals(session: SessionFacts) -> list[dict[str, Any]]:
    occurrences=[]
    by_turn={}
    for fact in session.facts:
        if fact.turn_id: by_turn.setdefault(fact.turn_id, []).append(fact)
    for turn_id, facts in by_turn.items():
        exploratory=[fact for fact in facts if fact.kind=="read" or _is_discovery(fact)]
        if len(exploratory)>=EXPLORATION_CALL_THRESHOLD:
            occurrences.append(_occurrence("R-EXP-01", session.session_id, exploratory[-1], turn_id=turn_id, count=len(exploratory)))
    if (not session.has_missing_timestamp and session.first_timestamp and
            session.last_timestamp):
        duration=(datetime.fromisoformat(session.last_timestamp)-datetime.fromisoformat(session.first_timestamp)).total_seconds()
        if duration>=SESSION_DURATION_SECONDS_THRESHOLD:
            fact=session.facts[-1] if session.facts else PatternFact(session.session_id,0,"",0)
            occurrences.append(_occurrence("R-SESSION-01",session.session_id,fact,duration_seconds=int(duration)))
    work_tokens=sum(_usage_total(item["usage"]) for item in session.final_token_usage.values())
    if session.final_token_usage and work_tokens>=SESSION_WORK_TOKEN_THRESHOLD:
        fact=session.facts[-1] if session.facts else PatternFact(session.session_id,0,"",0)
        occurrences.append(_occurrence("R-TOKEN-01",session.session_id,fact,tokens=work_tokens))
    for fact in session.facts:
        if fact.output_chars is not None and fact.output_chars>=LARGE_OUTPUT_CHAR_THRESHOLD:
            occurrences.append(_occurrence("R-OUT-01",session.session_id,fact,characters=fact.output_chars))
        if fact.web_call:
            occurrences.append(_occurrence("R-WEB-01", session.session_id, fact))
    subagents=[fact for fact in session.facts if fact.subagent_spawn]
    if len(subagents)>=SUBAGENT_SPAWN_THRESHOLD:
        occurrences.append(_occurrence("R-SUBAGENT-01",session.session_id,subagents[-1],count=len(subagents)))
    return occurrences

def detect_observations(scan: PatternScan) -> list[dict[str, Any]]:
    """Detect the three direct observations from a PatternScan."""
    occurrences = []
    scan.diagnostics["retry_candidates_suppressed"] = 0
    for session in scan.sessions:
        occurrences.extend(_detect_repeated_reads(session))
        retry_occurrences, suppressed = _detect_retries(session)
        occurrences.extend(retry_occurrences)
        scan.diagnostics["retry_candidates_suppressed"] += suppressed
        occurrences.extend(_detect_test_churn(session))
        occurrences.extend(_detect_frequency_signals(session))
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
            "count_scope": metadata.get("count_scope", "occurrences"),
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


def _detect_retries(session: SessionFacts) -> tuple[list[dict[str, Any]], int]:
    occurrences = []
    suppressed = 0
    previous_key = None
    previous_command = None
    for fact in session.facts:
        if fact.kind == "test":
            previous_key = None
            previous_command = None
            continue
        if fact.kind != "command" or not fact.command:
            continue
        if fact.command == previous_command and (not fact.failure_fingerprint or not previous_key):
            suppressed += 1
        if not fact.failure_fingerprint:
            previous_key = None
            previous_command = fact.command
            continue
        key = (fact.command, fact.failure_fingerprint)
        if key == previous_key:
            occurrences.append(_occurrence("R-RETRY-01", session.session_id, fact, command=fact.command))
        previous_key = key
        previous_command = fact.command
    return occurrences, suppressed


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


def _occurrence(rule_id: str, session_id: str, fact: PatternFact, **fields: Any) -> dict[str, Any]:
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
    fact.output_chars = _output_length(output)
    status, evidence = _failure_status(output)
    if status == "success":
        fact.failure_fingerprint = None
        if fact.kind == "mutation" or (fact.command and _MUTATION_RE.search(fact.command)):
            fact.successful_mutation = True
    elif status == "failure":
        digest = hashlib.sha256((evidence or "failed").encode("utf-8", "ignore")).hexdigest()[:16]
        fact.failure_fingerprint = "output:" + digest


def _failure_status(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        for key in ("exit_code", "exitCode", "returncode", "return_code", "code"):
            code = value.get(key)
            if isinstance(code, int) and not isinstance(code, bool):
                return ("success", None) if code == 0 else ("failure", f"exit_code:{code}")
        if value.get("success") is True or value.get("ok") is True:
            return "success", None
        if value.get("success") is False or value.get("ok") is False or value.get("failed") is True:
            return "failure", _status_evidence(value)
        status = str(value.get("status", "")).lower()
        if status in {"success", "succeeded", "completed", "ok"}:
            return "success", None
        if status in {"failure", "failed", "error", "errored"}:
            return "failure", _status_evidence(value)
        for nested in value.values():
            result = _failure_status(nested)
            if result[0] is not None:
                return result
        return None, None
    text = _output_text(value)
    if not text:
        return None, None
    match = re.search(r"(?:exit\s+code|exited\s+with\s+(?:code|status)|exit_code|return(?:ed)?\s+code|status)\s*[:=]?\s*(-?\d+)", text, re.I)
    if match:
        code = int(match.group(1))
        return ("success", None) if code == 0 else ("failure", f"exit_code:{code}")
    if re.search(r"\b(?:command|process|test|operation)\s+(?:has\s+)?failed\b|\b(?:failure|error|errored)\b", text, re.I):
        return "failure", re.sub(r"\s+", " ", text).strip()
    return None, None


def _status_evidence(value: dict[str, Any]) -> str:
    status = value.get("status") or ("failed" if value.get("failed") is True else "error")
    return str(status)
