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

from .pattern_catalog import (
    RULE_CATALOG as CATALOG_RULES,
    EXPLORATION_CALL_THRESHOLD,
    SESSION_DURATION_SECONDS_THRESHOLD,
    SESSION_WORK_TOKEN_THRESHOLD,
    LARGE_OUTPUT_CHAR_THRESHOLD,
    SUBAGENT_SPAWN_THRESHOLD,
    CONTEXT_GROWTH_MIN_TOKENS, CONTEXT_GROWTH_RUN_LENGTH,
    CONTEXT_UTILIZATION_THRESHOLD, UNCACHED_INPUT_THRESHOLD,
    CARRY_INPUT_INCREASE_THRESHOLD,
    CONTEXT_SNAPSHOT_RETENTION_LIMIT, CONTEXT_OUTPUT_EVENT_RETENTION_LIMIT,
)
from .pattern_context import ContextSnapshot, ToolOutputEvent, detect_context_signals, normalize_token_snapshot


_READ_TYPES = {"read", "read_file", "file_read", "open_file"}
_MUTATION_TYPES = {"mutation", "patch", "file_write", "write_file", "patch_apply_end"}
_READ_COMMAND_RE = re.compile(r"(?:Get-Content|cat|type|head|tail|sed)(?:\s|$)", re.I)
_TEST_RE = re.compile(r"(?:^|\s)(?:pytest|py\.test|unittest|npm\s+test|cargo\s+test|go\s+test)(?:\s|$)", re.I)
_TEST_MODULE_RE = re.compile(r"\b(?:python(?:3)?|py)\s+-m\s+(pytest|unittest)\b", re.I)
_MUTATION_RE = re.compile(r"(?:apply_patch|git\s+(?:apply|commit)|(?:set|add|out)-content|touch\s|mkdir\s|npm\s+install)", re.I)
RULE_CATALOG = CATALOG_RULES


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
        self.anonymous_token_snapshots: list[dict[str, int]] = []
        self.cumulative_session_tokens: int | None = None
        self.token_accounting_source: str | None = None
        self.has_turn_telemetry = False
        self.has_lineage_telemetry = False
        self.has_web_telemetry = False
        self.current_model: str | None = None
        self.model_epoch = 0
        self.context_snapshots: list[ContextSnapshot] = []
        self.tool_output_events: list[ToolOutputEvent] = []


class PatternScan:
    def __init__(self, status: str) -> None:
        self.status = status
        self.sessions: list[SessionFacts] = []
        self.files_scanned = 0
        self.malformed_records = 0
        self.file_errors: list[dict[str, str]] = []
        self.diagnostics: dict[str, Any] = {
            "retry_candidates_suppressed": 0,
            "frequency_turn_coverage_missing": 0,
            "frequency_lineage_coverage_missing": 0,
            "frequency_web_coverage_missing": 0,
        }


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

        sequence = [0]
        pending_calls: dict[tuple[str, str], PatternFact] = {}
        web_calls: dict[tuple[str, str], PatternFact] = {}
        for path in files:
            result.files_scanned += 1
            try:
                self._read_file(path, sessions, result, sequence, pending_calls, web_calls)
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

    def _read_file(self, path: Path, sessions: dict[str, SessionFacts], result: PatternScan,
                   sequence: list[int], pending_calls: dict[tuple[str, str], PatternFact],
                   web_calls: dict[tuple[str, str], PatternFact]) -> None:
        resolved = str(path.resolve())
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

                if _telemetry_value(record, payload, "turn_id", "turnId", "turn") is not None:
                    session.has_turn_telemetry = True
                if _telemetry_value(record, payload, "lineage", "parent_session_id", "parent_call_id", "parentCallId") is not None:
                    session.has_lineage_telemetry = True
                if (_telemetry_value(record, payload, "web_call", "web", "is_web") is not None or
                        _is_web_lifecycle(_string(payload.get("type")))):
                    session.has_web_telemetry = True

                event_type = _string(payload.get("type")) or _string(record.get("type"))
                if event_type == "turn_context":
                    context_model = _normalize_text(payload.get("model"))
                    if context_model and session.current_model != context_model:
                        if session.current_model is not None:
                            session.model_epoch += 1
                        session.current_model = context_model

                if payload.get("type") == "token_count":
                    self._retain_token_snapshot(record, payload, session, resolved, line_number, timestamp)
                    explicit_model = _model_from_token_record(record, payload)
                    if explicit_model and session.current_model != explicit_model:
                        if session.current_model is not None:
                            session.model_epoch += 1
                        session.current_model = explicit_model
                    snapshot = normalize_token_snapshot(
                        record, payload, session_id, sequence[0], resolved, line_number, timestamp,
                        model_id_override=session.current_model,
                        stream_epoch=session.model_epoch,
                    )
                    if snapshot is not None:
                        session.context_snapshots.append(snapshot)
                        if len(session.context_snapshots) > CONTEXT_SNAPSHOT_RETENTION_LIMIT:
                            del session.context_snapshots[0]
                        sequence[0] += 1

                event_type = _string(payload.get("type")) or _string(record.get("type"))
                if _is_web_lifecycle(event_type) and event_type == "web_search_end":
                    call_id = _string(payload.get("call_id"))
                    if call_id and (session_id, call_id) in web_calls:
                        web_fact = web_calls[(session_id, call_id)]
                        output = _telemetry_value(record, payload, "output", "result")
                        if output is not None:
                            web_fact.output_chars = _output_length(output)
                            session.tool_output_events.append(ToolOutputEvent(
                                session_id, sequence[0], resolved, line_number, timestamp,
                                _output_length(output) or 0, session.current_model,
                                session.model_epoch,
                            ))
                            if len(session.tool_output_events) > CONTEXT_OUTPUT_EVENT_RETENTION_LIMIT:
                                del session.tool_output_events[0]
                            sequence[0] += 1
                        continue

                if payload.get("type") in ("function_call_output", "custom_tool_call_output"):
                    call_id = _string(payload.get("call_id"))
                    if call_id and (session_id, call_id) in pending_calls:
                        _apply_call_output(pending_calls[(session_id, call_id)], payload.get("output"))
                    output = payload.get("output")
                    if output is not None:
                        session.tool_output_events.append(ToolOutputEvent(
                            session_id, sequence[0], resolved, line_number, timestamp,
                            _output_length(output) or 0, session.current_model,
                            session.model_epoch,
                        ))
                        if len(session.tool_output_events) > CONTEXT_OUTPUT_EVENT_RETENTION_LIMIT:
                            del session.tool_output_events[0]
                        sequence[0] += 1
                    continue

                fact = _fact_from_record(record, payload, session_id, sequence[0], resolved, line_number, timestamp)
                if fact is not None:
                    session.facts.append(fact)
                    sequence[0] += 1
                    call_id = _string(payload.get("call_id"))
                    if call_id and payload.get("type") in ("function_call", "custom_tool_call"):
                        pending_calls[(session_id, call_id)] = fact
                    if call_id and event_type == "web_search_call":
                        web_calls[(session_id, call_id)] = fact

    @staticmethod
    def _retain_token_snapshot(record: dict[str, Any], payload: dict[str, Any], session: SessionFacts,
                               filepath: str, line: int, timestamp: str | None) -> None:
        info = payload.get("info")
        usage = info.get("last_token_usage") if isinstance(info, dict) else None
        cumulative = _cumulative_session_total(info, payload, record)
        if cumulative is not None:
            session.cumulative_session_tokens = max(session.cumulative_session_tokens or 0, cumulative)
            session.token_accounting_source = "cumulative_session_total"
            return
        if not isinstance(usage, dict):
            return
        request_id = _string(record.get("requestId")) or _string(payload.get("requestId"))
        candidate = {"timestamp": timestamp, "source": {"filepath": filepath, "line": line}, "usage": _safe_usage(usage)}
        if request_id is None:
            # Without a request ID, snapshots cannot be safely assigned to
            # requests. Treat them as cumulative and retain the largest total;
            # summing them would count repeated snapshots as new work.
            session.anonymous_token_snapshots.append(candidate["usage"])
            session.token_accounting_source = "max_snapshot_without_request_id"
            return
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
    elif event_type in ("function_call", "custom_tool_call", "web_search", "web_fetch", "browser_search", "browser_fetch") or _is_web_lifecycle(event_type) or (event_type and re.search(r"\b(?:spawn_subagent|spawn_agent|subagent_spawn)\b", event_type, re.I)):
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


def _usage_total(usage: dict[str, int]) -> int | None:
    explicit = usage.get("total_tokens")
    if explicit is not None:
        return explicit
    input_tokens = usage.get("input_tokens")
    cached_input = usage.get("cached_input_tokens", 0)
    output_tokens = usage.get("output_tokens")
    if input_tokens is not None:
        if cached_input > input_tokens:
            return None
        total = input_tokens
    else:
        total = 0
    if output_tokens is not None:
        total += output_tokens
    elif usage.get("reasoning_output_tokens") is not None:
        total += usage["reasoning_output_tokens"]
    return total if total else None


def _cumulative_session_total(info: Any, payload: dict[str, Any], record: dict[str, Any]) -> int | None:
    for source in (info, payload, record):
        if not isinstance(source, dict):
            continue
        for key in ("total_tokens", "session_total_tokens", "cumulative_tokens"):
            value = source.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
        for key in ("total_token_usage", "session_token_usage", "cumulative_token_usage"):
            value = source.get(key)
            if isinstance(value, dict):
                # Component counters overlap (cached input is included in
                # input, and reasoning is included in output). Only an
                # explicit provider total is safe to treat as cumulative.
                total = value.get("total_tokens")
                if isinstance(total, int) and not isinstance(total, bool) and total >= 0:
                    return total
    return None


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


def _model_from_token_record(record: dict[str, Any], payload: dict[str, Any]) -> str | None:
    info = payload.get("info")
    if isinstance(info, dict):
        model = _normalize_text(info.get("model"))
        if model:
            return model
    return (_normalize_text(payload.get("model")) or
            _normalize_text(record.get("model")))


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
    if not value or value.startswith(("$", "-")) or "${" in value:
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
    if _is_web_lifecycle(event_type):
        return True
    text = " ".join(filter(None, (event_type, name, _string(payload.get("tool_name")))))
    return bool(re.search(r"\b(?:web_search|web_fetch|web\.run|browser_search|browser_fetch)\b", text, re.I))


def _is_web_lifecycle(event_type: str | None) -> bool:
    return event_type in {"web_search_call", "web_search_end"}

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
    if session.cumulative_session_tokens is not None:
        work_tokens = session.cumulative_session_tokens
    else:
        known_totals = [
            total for item in session.final_token_usage.values()
            if (total := _usage_total(item["usage"])) is not None
        ]
        work_tokens = sum(known_totals)
        if session.anonymous_token_snapshots:
            anonymous_totals = [
                total for item in session.anonymous_token_snapshots
                if (total := _usage_total(item)) is not None
            ]
            work_tokens += max(anonymous_totals, default=0)
    if (session.final_token_usage or session.anonymous_token_snapshots or
            session.cumulative_session_tokens is not None) and work_tokens>=SESSION_WORK_TOKEN_THRESHOLD:
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
    scan.diagnostics["frequency_turn_coverage_missing"] = 0
    scan.diagnostics["frequency_lineage_coverage_missing"] = 0
    scan.diagnostics["frequency_web_coverage_missing"] = 0
    for session in scan.sessions:
        occurrences.extend(_detect_repeated_reads(session))
        retry_occurrences, suppressed = _detect_retries(session)
        occurrences.extend(retry_occurrences)
        scan.diagnostics["retry_candidates_suppressed"] += suppressed
        occurrences.extend(_detect_test_churn(session))
        occurrences.extend(_detect_frequency_signals(session))
        context_occurrences, context_diagnostics = detect_context_signals(session)
        occurrences.extend(context_occurrences)
        for key, value in context_diagnostics.items():
            scan.diagnostics[key] = scan.diagnostics.get(key, 0) + value
        if session.facts and not session.has_turn_telemetry:
            scan.diagnostics["frequency_turn_coverage_missing"] += 1
        if session.facts and not session.has_lineage_telemetry:
            scan.diagnostics["frequency_lineage_coverage_missing"] += 1
        if session.facts and not session.has_web_telemetry:
            scan.diagnostics["frequency_web_coverage_missing"] += 1
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
        if "unit" in metadata:
            result = results[-1]
            result.update({
                "threshold": metadata.get("threshold"),
                "secondary_threshold": metadata.get("secondary_threshold"),
                "unit": metadata["unit"],
                "telemetry_required": metadata.get("telemetry_required", []),
                "telemetry_available": all(
                    item["example"].get("telemetry_available", False) for item in rule_occurrences
                ),
            })
            if rule_id.startswith(("R-CTX-", "R-CACHE-", "R-CARRY-")):
                scopes = {
                    (item["example"].get("model_id"), item["example"].get("stream_epoch"))
                    for item in rule_occurrences
                }
                result["source_model_scope"] = [
                    {"model_id": model_id, "stream_epoch": stream_epoch}
                    for model_id, stream_epoch in sorted(scopes, key=lambda item: (str(item[0]), item[1]))
                ]
    return sorted(results, key=lambda result: (-result["count"], result["id"]))


def _detect_repeated_reads(session: SessionFacts) -> list[dict[str, Any]]:
    by_target: dict[str, list[PatternFact]] = {}
    for fact in session.facts:
        if fact.kind == "read" and fact.target:
            by_target.setdefault(fact.target, []).append(fact)
    occurrences = []
    for target in sorted(by_target):
        # Treat the third read as the first actionable repeat; a second read
        # can be a normal verification step.
        for fact in by_target[target][2:]:
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
    match = re.search(r"(?:Get-Content|cat|type|head|tail|sed)\b(?P<args>.*)", command, re.I)
    if not match:
        return None
    tokens = re.findall(r"'[^']*'|\"[^\"]*\"|[^\s|;]+", match.group("args"))
    switches_with_values = {"-literalpath", "-path", "-filepath", "-include", "-exclude", "-filter", "-encoding"}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        unquoted = token[1:-1] if len(token) >= 2 and token[0] == token[-1] and token[0] in "'\"" else token
        lowered = unquoted.lower()
        if lowered.startswith("-"):
            if lowered in switches_with_values:
                index += 1
                if index >= len(tokens):
                    return None
                candidate = tokens[index]
                candidate = candidate[1:-1] if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "'\"" else candidate
                return _normalize_target(candidate)
            index += 1
            continue
        return _normalize_target(unquoted)
    return None

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
