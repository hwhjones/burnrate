"""Deterministic waste-signature analysis for normalized Codex traces."""

from collections import defaultdict
from datetime import datetime, timezone

from .normalize import normalize_events


class CodexWasteAnalyzer:
    """Produce evidence-backed pilot findings without content analysis."""

    def analyze(self, events: list[dict]) -> dict:
        """Analyze a normalized timeline and return deterministic findings."""
        normalized = (
            events if all("normalized" in event for event in events) else normalize_events(events)
        )
        timeline = sorted(normalized, key=_timeline_key)
        findings = []
        findings.extend(_repeated_commands(timeline))
        findings.extend(_repeated_discovery(timeline))
        findings.extend(_mutation_aware_repetition(timeline))
        findings.extend(_recurring_failures(timeline))
        findings.extend(_tokens_before_mutation(timeline))
        findings.extend(_duplicate_subagent_work(timeline))
        return {"findings": findings}


def _mutation_aware_repetition(events):
    findings = []
    findings.extend(_repeated_reads_without_mutation(events))
    findings.extend(_repeated_completed_commands_without_mutation(events))
    return findings


def _repeated_reads_without_mutation(events):
    groups = _groups(
        event for event in events
        if event.get("event_type") == "tool_call"
        and event.get("normalized", {}).get("command")
        and event.get("normalized", {}).get("read_path")
    )
    findings = []
    for (command, _path), evidence in groups.items():
        target = evidence[0]["normalized"]["read_path"]
        if len(evidence) < 2:
            continue
        pairs = _pairs_without_mutation(events, evidence, target)
        if not pairs:
            continue
        findings.append(_finding(
            "repeated_read_without_observed_mutation",
            "derived",
            "medium",
            "The same explicit read target recurred with no observed successful mutation to that target between attempts.",
            [item for pair in pairs for item in pair],
            command=command,
            read_path=target,
            attempts=len(pairs) + 1,
        ))
    return findings


def _repeated_completed_commands_without_mutation(events):
    groups = _groups(
        event for event in events
        if event.get("event_type") == "tool_output"
        and event.get("normalized", {}).get("command")
        and event.get("normalized", {}).get("exit_status")
    )
    findings = []
    for (command, path), evidence in groups.items():
        if len(evidence) < 2:
            continue
        pairs = _pairs_without_mutation(events, evidence, path)
        if not pairs:
            continue
        status = evidence[0]["normalized"]["exit_status"]
        if evidence[0].get("operation") == "discovery" and status == "success":
            kind = "repeated_repository_discovery_without_observed_mutation"
        else:
            kind = "repeated_failed_command_without_observed_mutation" if status.startswith("failure:") else "repeated_successful_command_without_observed_mutation"
        findings.append(_finding(
            kind,
            "derived",
            "medium",
            "The same completed command and status recurred with no observed relevant mutation between attempts.",
            [item for pair in pairs for item in pair],
            command=command,
            path=path,
            exit_status=status,
            attempts=len(pairs) + 1,
        ))
    return findings


def _pairs_without_mutation(all_events, evidence, target):
    pairs = []
    for first, second in zip(evidence, evidence[1:]):
        if not any(
            _is_relevant_mutation(event, target)
            for event in all_events
            if _timeline_key(first) < _timeline_key(event) < _timeline_key(second)
        ):
            pairs.append((first, second))
    return pairs


def _is_relevant_mutation(event, target):
    if event.get("operation") != "mutation" or event.get("normalized", {}).get("mutation_status") != "succeeded":
        return False
    mutation_paths = _path_values(event.get("normalized", {}).get("path"))
    target_paths = _path_values(target)
    return not target_paths or any(_paths_related(left, right) for left in mutation_paths for right in target_paths)


def _paths_related(left, right):
    return (left == right or left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/") or left.endswith("/" + right.lstrip("/")) or right.endswith("/" + left.lstrip("/")))

def _repeated_commands(events):
    groups = _groups(
        event
        for event in events
        if event.get("event_type") == "tool_call"
        and event.get("normalized", {}).get("command")
    )
    findings = []
    for (command, path), evidence in groups.items():
        if len(evidence) < 2:
            continue
        findings.append(_finding(
            "repeated_command_attempt",
            "observed",
            "high",
            "At least two tool-call events have the exact same normalized command and path.",
            evidence,
            command=command,
            path=path,
            attempts=len(evidence),
            sessions=_sessions(evidence),
        ))
    return findings


def _repeated_discovery(events):
    groups = _groups(
        event
        for event in events
        if event.get("event_type") == "tool_call"
        and event.get("operation") == "discovery"
    )
    findings = []
    for (command, path), evidence in groups.items():
        if len(evidence) < 2:
            continue
        findings.append(_finding(
            "repeated_repository_discovery",
            "observed",
            "high",
            "At least two discovery tool calls have the exact same normalized command and path.",
            evidence,
            command=command,
            path=path,
            attempts=len(evidence),
            sessions=_sessions(evidence),
        ))
    return findings


def _recurring_failures(events):
    groups = defaultdict(list)
    for event in events:
        normalized = event.get("normalized", {})
        status = normalized.get("exit_status")
        command = normalized.get("command")
        error = normalized.get("error_text")
        error_evidence = normalized.get("error_evidence") or error
        if event.get("event_type") != "tool_output" or not command or not error_evidence:
            continue
        if not isinstance(status, str) or not status.startswith("failure:"):
            continue
        groups[(command, status, error_evidence)].append(event)

    findings = []
    for (command, status, error), evidence in groups.items():
        if len(evidence) < 2:
            continue
        findings.append(_finding(
            "recurring_failure",
            "derived",
            "high",
            "At least two tool outputs share the exact normalized command, failure status, and error text.",
            evidence,
            command=command,
            exit_status=status,
            error_evidence=error,
            occurrences=len(evidence),
            sessions=_sessions(evidence),
        ))
    return findings


def _tokens_before_mutation(events):
    by_session = defaultdict(list)
    for event in events:
        session = event.get("normalized", {}).get("session_id", "<unknown-session>")
        by_session[session].append(event)

    findings = []
    for session, session_events in sorted(by_session.items()):
        first_mutation = next(
            (
                event for event in session_events
                if event.get("operation") == "mutation"
                and event.get("normalized", {}).get("mutation_status") == "succeeded"
            ),
            None,
        )
        if first_mutation is None:
            findings.append(_finding(
                "tokens_before_first_successful_mutation",
                "unavailable",
                "none",
                "No observed successful repository mutation exists for this session.",
                session_events,
                session_id=session,
            ))
            continue
        before = [
            event for event in session_events
            if _timeline_key(event) < _timeline_key(first_mutation)
            and event.get("event_type") == "token_count"
            and _token_total(event) is not None
        ]
        if not before:
            findings.append(_finding(
                "tokens_before_first_successful_mutation",
                "unavailable",
                "none",
                "No usable token snapshot precedes the first observed successful repository mutation.",
                [first_mutation],
                session_id=session,
            ))
            continue
        latest = max(before, key=_timeline_key)
        findings.append(_finding(
            "tokens_before_first_successful_mutation",
            "derived",
            "high",
            "The last cumulative token snapshot before the first observed successful repository mutation supplies orientation evidence; it is not a waste finding.",
            [latest, first_mutation],
            session_id=session,
            tokens_consumed=_token_total(latest),
            first_mutation_source=_source(first_mutation),
            interpretation="orientation evidence",
        ))
    return findings


def _duplicate_subagent_work(events):
    by_parent = defaultdict(lambda: defaultdict(list))
    for event in events:
        normalized = event.get("normalized", {})
        agent = normalized.get("agent_id")
        parent = normalized.get("parent_agent_id")
        if agent and parent:
            by_parent[parent][agent].append(event)

    findings = []
    for parent, agents in sorted(by_parent.items()):
        ordered_agents = sorted(agents)
        for index, first_agent in enumerate(ordered_agents):
            for second_agent in ordered_agents[index + 1:]:
                evidence, signals = _duplication_evidence(
                    agents[first_agent], agents[second_agent]
                )
                if len(signals) < 2:
                    continue
                confidence = "high" if len(signals) >= 3 else "medium"
                findings.append(_finding(
                    "probable_duplicated_subagent_work",
                    "heuristic",
                    confidence,
                    "Shared parent lineage plus " + ", ".join(signals) + ".",
                    evidence,
                    parent_agent_id=parent,
                    agents=[first_agent, second_agent],
                    supporting_evidence=signals,
                ))
    return findings


def _duplication_evidence(first_events, second_events):
    evidence = []
    signals = []
    first_commands = _values(first_events, "command")
    second_commands = _values(second_events, "command")
    shared_commands = first_commands & second_commands
    first_paths = _values(first_events, "path")
    second_paths = _values(second_events, "path")
    shared_paths = first_paths & second_paths
    if shared_commands:
        signals.append("matching normalized command")
    if shared_paths:
        signals.append("matching normalized path")
    if _overlaps_in_time(first_events, second_events):
        signals.append("events within 30 minutes")
    first_patches = _patch_paths(first_events)
    second_patches = _patch_paths(second_events)
    if first_patches & second_patches:
        signals.append("overlapping patch path")
    if signals:
        evidence = [
            event for event in first_events + second_events
            if (
                event.get("normalized", {}).get("command") in shared_commands
                or _path_membership(event.get("normalized", {}).get("path"), shared_paths)
                or event.get("normalized", {}).get("path") in first_patches & second_patches
            )
        ]
    return evidence or first_events + second_events, signals


def _groups(events):
    groups = defaultdict(list)
    for event in events:
        normalized = event.get("normalized", {})
        command = normalized.get("command")
        path = normalized.get("path")
        groups[(command, _path_key(path))].append(event)
    return groups


def _values(events, field):
    values = set()
    for event in events:
        value = event.get("normalized", {}).get(field)
        if isinstance(value, str):
            values.add(value)
        elif field == "path" and isinstance(value, list):
            values.update(item for item in value if isinstance(item, str))
    return values


def _patch_paths(events):
    return {
        path
        for event in events
        if event.get("event_type") == "patch"
        for path in _path_values(event.get("normalized", {}).get("path"))
    }


def _path_values(value):
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def _path_key(value):
    if isinstance(value, list):
        return tuple(value)
    return value


def _path_membership(value, paths):
    return bool(_path_values(value) & paths)


def _overlaps_in_time(first_events, second_events):
    first_times = [_parsed_time(event) for event in first_events]
    second_times = [_parsed_time(event) for event in second_events]
    first_times = [value for value in first_times if value is not None]
    second_times = [value for value in second_times if value is not None]
    return any(abs((left - right).total_seconds()) <= 30 * 60 for left in first_times for right in second_times)


def _token_total(event):
    snapshot = event.get("token_snapshot")
    if not isinstance(snapshot, dict):
        return None
    total = snapshot.get("total_tokens")
    return total if isinstance(total, int) and not isinstance(total, bool) and total >= 0 else None


def _timeline_key(event):
    parsed = _parsed_time(event)
    source = event.get("source", {})
    return (
        parsed is not None,
        parsed or datetime.min.replace(tzinfo=timezone.utc),
        source.get("filepath", ""),
        source.get("line", 0),
    )


def _parsed_time(event):
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    try:
        value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _finding(kind, label, confidence, confidence_rule, evidence, **details):
    return {
        "kind": kind,
        "label": label,
        "confidence": confidence,
        "confidence_rule": confidence_rule,
        "evidence": [_source(event) for event in evidence],
        **details,
    }


def _source(event):
    return event.get("source", {})


def _sessions(events):
    return sorted({event.get("normalized", {}).get("session_id", "<unknown-session>") for event in events})
