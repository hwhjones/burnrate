"""Deterministic waste-signature analysis for normalized Codex traces."""

from collections import defaultdict
import hashlib
import re
from datetime import datetime, timezone

from .normalize import normalize_events
from .correlation import BOUNDARY_RULES, correlate_messages, segment_episodes
from .catalog import (attach_catalog_metadata, compute_baselines, lower_signal_candidates, deduplicate_catalog_findings, habit_summaries)


class CodexWasteAnalyzer:
    """Produce evidence-backed findings, adding content only when opted in."""

    def analyze(self, events: list[dict]) -> dict:
        """Analyze a normalized timeline and return deterministic findings."""
        normalized = (
            events if all("normalized" in event for event in events) else normalize_events(events)
        )
        timeline = sorted(normalized, key=_timeline_key)
        episodes = segment_episodes(timeline)
        scoped_timeline = _attach_episode_scope(timeline, episodes)
        findings = []
        findings.extend(_repeated_commands(timeline))
        findings.extend(_repeated_discovery(timeline))
        findings.extend(_mutation_aware_repetition(scoped_timeline))
        findings.extend(_repeated_test_churn(scoped_timeline))
        findings.extend(_recurring_failures(timeline))
        findings.extend(_automation_failure_episodes(timeline))
        findings.extend(_tokens_before_mutation(timeline))
        findings.extend(_duplicate_subagent_work(scoped_timeline))
        correlation = correlate_messages(timeline, episodes)
        findings.extend(correlation["candidates"])
        for finding in findings:
            finding.setdefault("evidence_kind", "structured")
            attach_catalog_metadata(finding, scoped_timeline)
        candidate_findings = deduplicate_catalog_findings(findings, scoped_timeline)
        baselines = compute_baselines(timeline)
        return {
            "findings": findings,
            "candidate_findings": candidate_findings,
            "candidate_count": len(candidate_findings),
            "habit_summaries": habit_summaries(candidate_findings, scoped_timeline),
            "episodes": episodes,
            "baselines": baselines,
            "lower_signal_candidates": lower_signal_candidates(timeline, baselines),
            "boundary_rules": BOUNDARY_RULES,
            "similarity_ladder": correlation["similarity_ladder"],
            "active_similarity_rules": correlation.get("active_similarity_rules", []),
            "message_matches": correlation["message_matches"],
        }


def _candidate_groups(events, *, target_only=False):
    groups = defaultdict(list)
    for event in events:
        normalized = event.get("normalized", {})
        command = normalized.get("command")
        target = normalized.get("read_path") or command
        path = _path_key(normalized.get("path"))
        if target:
            groups[(_analysis_scope(event), None if target_only else command, path, target)].append(event)
    return groups


def _analysis_scope(event):
    return event.get("_analysis_scope", (
        event.get("normalized", {}).get("session_id"),
        None,
    ))


def _repository_key(value):
    paths = value if isinstance(value, list) else [value]
    path = next((item for item in paths if isinstance(item, str)), None)
    if not path:
        return None
    if re.search(r"\.[a-z0-9]{1,8}$", path, re.IGNORECASE):
        return path.rsplit("/", 1)[0] or "/"
    return path


def _attach_episode_scope(events, episodes):
    membership = {
        (item.get("filepath"), item.get("line")): episode.get("episode_id")
        for episode in episodes
        for item in episode.get("event_evidence", [])
    }
    task_scopes = {}
    task_number = 0
    task_boundaries = {"first_event", "explicit_user_request", "agent_handoff", "idle_gap", "repository_or_workdir_change"}
    for episode in episodes:
        if task_number == 0 or task_boundaries.intersection(episode.get("boundary_rules", [])):
            task_number += 1
        task_scopes[episode.get("episode_id")] = f"task-{task_number}"
    scoped = []
    for event in events:
        source = event.get("source", {})
        episode_id = membership.get((source.get("filepath"), source.get("line")))
        scope = (
            event.get("normalized", {}).get("session_id"),
            task_scopes.get(episode_id),
        )
        scoped.append(dict(event, _analysis_scope=scope))
    return scoped


def _mutation_aware_repetition(events):
    findings = []
    findings.extend(_repeated_reads_without_mutation(events))
    findings.extend(_repeated_completed_commands_without_mutation(events))
    return findings


def _repeated_reads_without_mutation(events):
    groups = _candidate_groups(
        (
            event for event in events
            if event.get("event_type") == "tool_call"
            and event.get("normalized", {}).get("read_path")
        ),
        target_only=True,
    )
    findings = []
    for (_scope, _command, _path, target), evidence in groups.items():
        target = evidence[0]["normalized"]["read_path"]
        command = evidence[0].get("normalized", {}).get("command")
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
    groups = _candidate_groups(
        event for event in events
        if event.get("event_type") == "tool_output"
        and event.get("normalized", {}).get("command")
        and event.get("normalized", {}).get("exit_status")
    )
    findings = []
    for (_scope, command, path, _target), evidence in groups.items():
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


def _repeated_test_churn(events):
    groups = _candidate_groups(
        event for event in events
        if event.get("event_type") == "tool_output"
        and event.get("operation") == "test"
        and event.get("normalized", {}).get("command")
    )
    findings = []
    for (_scope, command, path, _target), evidence in groups.items():
        if len(evidence) < 2:
            continue
        pairs = _pairs_without_mutation(events, evidence, path)
        if not pairs:
            continue
        findings.append(_finding(
            "test_churn_without_relevant_mutation",
            "derived",
            "medium",
            "The same normalized test command recurred without an observed relevant successful mutation between outcomes.",
            [item for pair in pairs for item in pair],
            command=command,
            path=path,
            attempts=len(pairs) + 1,
            test_outcomes=sorted({item.get("normalized", {}).get("exit_status") for item in evidence}),
        ))
    return findings


def _pairs_without_mutation(all_events, evidence, target):
    pairs = []
    for first, second in zip(evidence, evidence[1:]):
        scope = _analysis_scope(first)
        if not any(
            _analysis_scope(event) == scope and _is_relevant_mutation(event, target)
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


def _automation_failure_episodes(events):
    """Correlate repeated structured failures into privacy-bounded episodes."""
    groups = defaultdict(list)
    for event in events:
        normalized = event.get("normalized", {})
        status = normalized.get("exit_status")
        command = normalized.get("command")
        signature_command = _episode_command_key(command)
        evidence = normalized.get("error_fingerprint") or normalized.get("error_text") or normalized.get("error_evidence") or "exit-status-only"
        if event.get("event_type") != "tool_output" or not command:
            continue
        if not isinstance(status, str) or not status.startswith("failure:"):
            continue
        groups[(signature_command, status, evidence)].append(event)

    findings = []
    for (command, status, error), evidence in groups.items():
        sessions = _sessions(evidence)
        if len(evidence) < 2 or len(sessions) < 2:
            continue
        episode_type = _episode_type(command, error)
        overlap = _sessions_overlap(evidence)
        confidence = "high" if overlap else "medium"
        later_success = _later_success(events, evidence)
        findings.append(_finding(
            "automation_failure_episode",
            "observed",
            confidence,
            "Repeated structured failure across distinct runs; confidence is high only when run timestamps overlap.",
            evidence,
            episode_type=episode_type,
            operation="automation",
            command_signature="cmd-" + hashlib.sha256(command.encode("utf-8")).hexdigest()[:12],
            exit_status=status,
            error_evidence="error-text-present" if error != "exit-status-only" else "exit-status-only",
            error_fingerprint="err-" + hashlib.sha256(error.encode("utf-8")).hexdigest()[:12],
            run_count=len(sessions),
            sessions=sessions,
            recovery="later_success_observed" if later_success else "none_observed",
            terminal_status="success_after_failure" if later_success else "failure_or_unknown",
            time_window=_time_window(evidence),
        ))
    return findings


def _episode_command_key(command):
    """Collapse dated import filenames for cross-run comparison."""
    return re.sub(r"(gmail|linkedin)-\d{4}-\d{2}-\d{2}", r"\1-<date>", command or "")

def _episode_type(command, error):
    text = (command + " " + error).lower()
    if "checkpoint" in text or "validate-import" in text or "already" in text and "import" in text:
        return "duplicate_checkpoint_import"
    if "no such file" in text or "cannot find path" in text or "not found" in text or "missing-path" in text or "$env:codex_home" in text or "<home>/automations" in text:
        return "stale_or_missing_path"
    if "no such column" in text or "operationalerror" in text or "schema-query-error" in text:
        return "schema_query_mismatch"
    if "syntaxerror" in text or "unterminated" in text or "not recognized" in text or "terminator" in text or "shell-parse-error" in text:
        return "shell_quoting_failure"
    return "recurring_command_failure"


def _sessions_overlap(events):
    times = [_parsed_time(event) for event in events]
    times = [time for time in times if time is not None]
    return bool(times) and (max(times) - min(times)).total_seconds() <= 30 * 60


def _later_success(all_events, failures):
    failure_sessions = set(_sessions(failures))
    last_failure = max((_parsed_time(event) for event in failures if _parsed_time(event)), default=None)
    if last_failure is None:
        return False
    return any(
        event.get("event_type") == "tool_output"
        and event.get("normalized", {}).get("exit_status") == "success"
        and event.get("normalized", {}).get("session_id") in failure_sessions
        and (_parsed_time(event) or last_failure) > last_failure
        and any(token in (event.get("normalized", {}).get("command") or "").lower() for token in ("audit", "report", "summary"))
        for event in all_events
    )


def _time_window(events):
    times = sorted(time for time in (_parsed_time(event) for event in events) if time is not None)
    if not times:
        return None
    return {"start": times[0].isoformat(), "end": times[-1].isoformat()}

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
