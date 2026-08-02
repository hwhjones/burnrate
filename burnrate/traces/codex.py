"""Privacy-bounded reader for the experimental Codex trace pilot.

The reader deliberately does not return natural-language message, response,
reasoning, patch, standard-output, or tool-output bodies.  Its schema is
restricted to structured execution evidence needed by the pilot.
"""

import json
import re
from collections.abc import Mapping
from pathlib import Path


_TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
_PATH_FIELDS = ("path", "file_path", "filepath", "workdir", "cwd")
_EXIT_FIELDS = ("exit_code", "exit_status", "status_code")
_ERROR_FIELDS = ("error", "stderr", "error_message")


class CodexTraceReader:
    """Read a constrained timeline from Codex JSONL session logs.

    This is experimental and provider-specific.  It is not a ``BaseParser``:
    it does not calculate tokens or cost, produce a summary, or alter the
    stable v0.1.1 parser path.
    """

    def __init__(self, log_path: str = "~/.codex/sessions/") -> None:
        self.log_dir = Path(log_path).expanduser()
        self.events = []
        self.skip_counts = {}
        self.file_read_errors = []
        self.content_manifest = []
        self.include_content = False
        self.content_roles = {"user", "agent"}

    def parse(self, *, include_content=False, content_roles=None) -> list[dict]:
        """Return structured events, optionally including selected message text.

        Content interrogation is opt-in. The default path retains the original
        body-free event contract. ``content_manifest`` records every selected
        source field read when content is enabled.
        """
        self.events = []
        self.skip_counts = {
            "malformed_json": 0,
            "non_object_json": 0,
            "invalid_record_shape": 0,
        }
        self.file_read_errors = []
        self.content_manifest = []
        self.include_content = bool(include_content)
        requested_roles = content_roles or {"user", "agent"}
        self.content_roles = {
            "agent" if role == "assistant" else role
            for role in requested_roles
            if role in {"user", "agent", "assistant"}
        }

        for file_path in self._discover_jsonl_files():
            try:
                self._parse_file(file_path)
            except (OSError, UnicodeError) as error:
                self.file_read_errors.append(
                    {"filepath": str(file_path), "error": error.__class__.__name__}
                )
        return self.events

    def _discover_jsonl_files(self) -> list[Path]:
        try:
            if self.log_dir.is_file():
                return [self.log_dir] if self.log_dir.suffix == ".jsonl" else []
            if not self.log_dir.is_dir():
                return []
            return sorted(self.log_dir.rglob("*.jsonl"))
        except OSError:
            return []

    def _parse_file(self, file_path: Path) -> None:
        session_id = None
        calls = {}
        with file_path.open("r", encoding="utf-8-sig") as source:
            for source_line, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    self.skip_counts["malformed_json"] += 1
                    continue
                if not isinstance(record, Mapping):
                    self.skip_counts["non_object_json"] += 1
                    continue

                event, discovered_session, call = self._extract_event(
                    record, session_id, calls
                )
                session_id = discovered_session or session_id
                if call is not None:
                    calls[call[0]] = call[1]
                if event is not None:
                    event["source"] = {
                        "filepath": str(file_path.resolve()),
                        "line": source_line,
                    }
                    content_field = event.pop("_content_source_field", None)
                    if content_field is not None:
                        self.content_manifest.append({
                            "filepath": event["source"]["filepath"],
                            "line": source_line,
                            "event_type": event.get("event_type"),
                            "role": event.get("message_role"),
                            "field": content_field,
                        })
                    self.events.append(event)

    def _extract_event(self, record, current_session, calls):
        record_type = record.get("type")
        payload = record.get("payload")
        if record_type == "session_meta":
            if not isinstance(payload, Mapping):
                self.skip_counts["invalid_record_shape"] += 1
                return None, current_session, None
            return None, _string(payload.get("id")) or current_session, None

        if not isinstance(payload, Mapping):
            # Natural-language legacy records and response bodies are ignored.
            return None, current_session, None

        session_id = (
            _string(record.get("session_id"))
            or _string(record.get("sessionId"))
            or _string(payload.get("session_id"))
            or current_session
        )
        base = _lineage(record, payload, session_id)
        payload_type = _string(payload.get("type"))

        if (
            self.include_content
            and record_type == "event_msg"
            and payload_type in {"user_message", "agent_message"}
        ):
            role = "user" if payload_type == "user_message" else "agent"
            if role not in self.content_roles:
                return None, session_id, None
            field, message = _message_text(payload)
            if field is not None and message is not None:
                return (
                    dict(
                        base,
                        event_type=payload_type,
                        message_role=role,
                        message_text=message,
                        _content_source_field=field,
                    ),
                    session_id,
                    None,
                )

        if record_type == "response_item" and payload_type in {
            "function_call",
            "custom_tool_call",
        }:
            event = dict(base, event_type="tool_call")
            tool_name = _string(payload.get("name"))
            if tool_name is not None:
                event["tool_name"] = tool_name
            arguments = _json_mapping(payload.get("arguments", payload.get("input")))
            _add_call_fields(event, arguments)
            call_id = _string(payload.get("call_id"))
            return event, session_id, (call_id, event) if call_id else None

        if record_type == "response_item" and payload_type in {
            "function_call_output",
            "custom_tool_call_output",
        }:
            event = dict(base, event_type="tool_output")
            call = calls.get(_string(payload.get("call_id")), {})
            for key in ("tool_name", "command", "path"):
                if key in call:
                    event[key] = call[key]
            if "read_path" in call:
                event["read_path"] = call["read_path"]
            output = _json_mapping(payload.get("output")) or _output_envelope(
                payload.get("output")
            )
            _add_output_fields(event, output)
            return event, session_id, None

        if record_type == "event_msg" and payload_type == "token_count":
            info = payload.get("info")
            if not isinstance(info, Mapping):
                self.skip_counts["invalid_record_shape"] += 1
                return None, session_id, None
            snapshot = _token_snapshot(info.get("last_token_usage"))
            if not snapshot:
                self.skip_counts["invalid_record_shape"] += 1
                return None, session_id, None
            return dict(base, event_type="token_count", token_snapshot=snapshot), session_id, None

        if record_type == "event_msg" and payload_type == "patch_apply_end":
            event = dict(base, event_type="patch")
            success = payload.get("success")
            if isinstance(success, bool):
                event["mutation_status"] = "succeeded" if success else "failed"
            elif _string(payload.get("status")) is not None:
                event["mutation_status"] = payload["status"]
            paths = _patch_paths(payload.get("changes"))
            if paths:
                event["path"] = paths[0] if len(paths) == 1 else paths
            _add_output_fields(event, payload)
            return event, session_id, None

        # Messages and reasoning are intentionally not represented.
        return None, session_id, None


def _message_text(payload):
    """Return one supported message field without inspecting tool bodies."""
    for field in ("message", "text", "content"):
        value = payload.get(field)
        if isinstance(value, str) and value:
            return f"payload.{field}", value
        if field == "content" and isinstance(value, list):
            parts = [
                item.get("text")
                for item in value
                if isinstance(item, Mapping)
                and isinstance(item.get("text"), str)
                and item.get("text")
            ]
            if parts:
                return "payload.content[].text", "\n".join(parts)
    return None, None

def _lineage(record, payload, session_id):
    event = {}
    if session_id is not None:
        event["session_id"] = session_id
    agent_id = _string(record.get("agent_id")) or _string(payload.get("agent_id"))
    parent_agent_id = _string(record.get("parent_agent_id")) or _string(
        payload.get("parent_agent_id")
    )
    if agent_id is not None:
        event["agent_id"] = agent_id
    if parent_agent_id is not None:
        event["parent_agent_id"] = parent_agent_id
    timestamp = _string(record.get("timestamp"))
    if timestamp is not None:
        event["timestamp"] = timestamp
    return event


def _add_call_fields(event, arguments):
    if not isinstance(arguments, Mapping):
        return
    command = _string(arguments.get("command"))
    if command is not None:
        event["command"] = command
        read_path = _extract_read_path(command)
        if read_path is not None:
            event["read_path"] = read_path
    path = _first_path(arguments)
    if path is not None:
        event["path"] = path


def _add_output_fields(event, output):
    if not isinstance(output, Mapping):
        return
    for field in _EXIT_FIELDS:
        value = output.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            event["exit_status"] = value
            break
    for field in _ERROR_FIELDS:
        value = _string(output.get(field))
        if value is not None:
            event["error_text"] = value
            break
    if output.get("error_evidence"):
        event["error_evidence"] = output["error_evidence"]
    if output.get("error_fingerprint"):
        event["error_fingerprint"] = output["error_fingerprint"]


def _output_envelope(value):
    """Extract status markers without retaining the tool-output body."""
    if not isinstance(value, str):
        return None
    match = re.search(r"(?im)^\s*exit\s+code\s*:\s*(-?\d+)\b", value)
    if match is None:
        return None
    status = int(match.group(1))
    return {
        "exit_status": status,
        "error_fingerprint": _error_fingerprint(value),
        "error_evidence": (
            "stderr-present"
            if re.search(r"(?i)\bstderr\b|\bcommand failed\b", value)
            else None
        ),
    }
def _error_fingerprint(value):
    """Extract a stable error category, never the output body."""
    text = value.lower()
    patterns = [(r"already checkpointed|duplicate checkpoint", "duplicate-checkpoint"), (r"no such column|operationalerror", "schema-query-error"), (r"cannot find path|no such file|not found", "missing-path"), (r"syntaxerror|unterminated|terminator|not recognized", "shell-parse-error"), (r"zero .*cards parsed|no .*cards parsed", "zero-cards-parsed")]
    for pattern, label in patterns:
        if re.search(pattern, text):
            return label
    return None

def _token_snapshot(value):
    if not isinstance(value, Mapping):
        return {}
    return {
        field: amount
        for field in _TOKEN_FIELDS
        if isinstance((amount := value.get(field)), int) and not isinstance(amount, bool)
    }


def _patch_paths(changes):
    if not isinstance(changes, Mapping):
        return []
    return [path for path in changes if isinstance(path, str) and path]


def _first_path(values):
    for field in _PATH_FIELDS:
        path = _string(values.get(field))
        if path is not None:
            return path
    return None


def _extract_read_path(command):
    """Extract only explicit file targets from recognized read commands."""
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

def _json_mapping(value):
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _string(value):
    return value if isinstance(value, str) and value else None
