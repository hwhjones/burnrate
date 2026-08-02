"""Stable, review-first candidate catalog for milestone 1d."""

from collections import Counter
from datetime import datetime, timezone


CATALOG_SCHEMA = "codex-candidate-catalog-v1"

CATALOG_RULES = {
    "C1D-READ-01": {
        "pattern": "re-reading the same file without relevant mutation",
        "required_evidence": ["repeated normalized read target", "source-linked read events", "no relevant successful mutation"],
        "exclusions": ["successful relevant mutation between reads", "missing read target", "low-information message only"],
        "derivation": "same explicit read target recurs before a relevant successful mutation",
        "unavailable_conditions": ["read target unavailable", "mutation evidence unavailable"],
        "possible_intervention": "Reference the earlier read when its evidence remains current.",
    },
    "C1D-RET-01": {
        "pattern": "ineffective retry loop",
        "required_evidence": ["same normalized command", "same failure status and error fingerprint", "no intervening progress"],
        "exclusions": ["different approach", "successful mutation or test between retries", "missing failure fingerprint"],
        "derivation": "a normalized failure repeats without an observed progress signal",
        "unavailable_conditions": ["failure status unavailable", "progress evidence unavailable"],
        "possible_intervention": "Change the approach before repeating the same attempt.",
    },
    "C1D-TEST-01": {
        "pattern": "test churn without relevant mutation",
        "required_evidence": ["repeated normalized test command", "test outcomes", "no relevant successful mutation"],
        "exclusions": ["relevant mutation between tests", "different test target", "test outcome unavailable"],
        "derivation": "the same test target recurs without a relevant successful mutation",
        "unavailable_conditions": ["test classification unavailable", "mutation evidence unavailable"],
        "possible_intervention": "Make or inspect a relevant change before retesting.",
    },
    "C1D-EXP-01": {
        "pattern": "duplicated exploration, including semantic sibling-subagent overlap",
        "required_evidence": ["repeated exploration target or sibling lineage", "matching informative message or normalized execution", "shared execution anchor", "no successful mutation or test progress"],
        "exclusions": ["similar wording alone", "lineage alone", "different scope with progress", "successful mutation or test observed"],
        "derivation": "independent or repeated exploration shares semantic and execution anchors without an observed progress signal",
        "unavailable_conditions": ["agent lineage unavailable", "message content not opted in", "execution anchor unavailable"],
        "possible_intervention": "Narrow or divide the investigative scope.",
    },
}


LOWER_SIGNAL_RULES = {
    "C1F-CTX-01": ("topic drift / marathon session", "semantic task-boundary interpretation unavailable", "candidate"),
    "C1F-CTX-02": ("compaction overrun / token pile-up", "compaction intent and context-limit evidence unavailable", "candidate"),
    "C1F-OUT-01": ("unused verbose response", "output-size and downstream-use evidence unavailable", "candidate"),
    "C1F-OUT-02": ("full log or stdout flood", "output-size and downstream-use evidence unavailable", "candidate"),
    "C1F-RES-01": ("stranded web or knowledge results", "downstream-use evidence unavailable", "signal"),
    "C1F-CACHE-01": ("cache/context discontinuity", "cache/model/effort transition and baseline unavailable", "candidate"),
    "C1F-EXP-02": ("main-thread exploration pile-up", "task-decomposition context unavailable", "candidate"),
    "C1F-EXP-03": ("subagent overuse", "progress linkage and downstream-use evidence unavailable", "signal"),
}


def rule_for_finding(finding):
    """Map an existing structured/combined finding to one stable 1d rule."""
    kind = finding.get("kind")
    if kind == "repeated_read_without_observed_mutation":
        return "C1D-READ-01"
    if kind == "repeated_investigation_without_progress":
        return "C1D-EXP-01"
    if kind in {"repeated_failed_command_without_observed_mutation", "ineffective_retry_loop"}:
        return "C1D-RET-01"
    if kind == "test_churn_without_relevant_mutation":
        return "C1D-TEST-01"
    if kind in {"probable_duplicated_subagent_work", "probable_semantic_subagent_duplication"}:
        return "C1D-EXP-01"
    return None


def attach_catalog_metadata(finding, events):
    """Annotate a finding without converting a candidate into a waste claim."""
    rule_id = rule_for_finding(finding)
    if not rule_id:
        return finding
    rule = CATALOG_RULES[rule_id]
    evidence = _evidence_events(finding, events)
    finding.update({
        'try_next_experiment': rule['possible_intervention'],
        'intervention_status': 'unconfirmed_experiment',
        "catalog_schema": CATALOG_SCHEMA,
        "candidate_id": rule_id,
        "candidate_status": "candidate",
        "pattern": rule["pattern"],
        "required_evidence": list(rule["required_evidence"]),
        "exclusions": list(rule["exclusions"]),
        "derivation": rule["derivation"],
        "unavailable_conditions": list(rule["unavailable_conditions"]),
        "possible_intervention": rule["possible_intervention"],
        "confirmation_required": True,
        "metrics": transparent_metrics(evidence),
        "baseline": unavailable_baseline(),
    })
    return finding


def unavailable_baseline():
    """Explicitly represent the missing cross-window baseline instead of guessing."""
    return {
        "current_value_source": "candidate_metrics",
        "baseline_window": None,
        "evidence_available": False,
        "sample_size": 0,
        "status": "unavailable",
    }


def transparent_metrics(events):
    """Return separate metrics from distinct source events, never a score."""
    unique = {}
    for event in events:
        source = event.get("source", {})
        key = (source.get("filepath"), source.get("line"))
        unique[key] = event
    events = list(unique.values())
    times = sorted(value for value in (_time(event) for event in events) if value is not None)
    snapshots = [
        event.get("token_snapshot", {}).get("total_tokens")
        for event in events
        if isinstance(event.get("token_snapshot"), dict)
        and isinstance(event.get("token_snapshot", {}).get("total_tokens"), int)
    ]
    call_count = sum(event.get("event_type") == "tool_call" for event in events)
    output_count = sum(event.get("event_type") == "tool_output" for event in events)
    attempts = max(call_count, output_count)
    return {
        "token_exposure": max(snapshots) - min(snapshots) if len(snapshots) >= 2 else None,
        "output_size": sum(_output_size(event) for event in events) or None,
        "attempts": attempts or None,
        "retries": max(0, attempts - 1) if attempts else None,
        "repeated_operations": len(events) or None,
        "elapsed_time_seconds": (times[-1] - times[0]).total_seconds() if len(times) >= 2 else None,
        "cache_changes": None,
        "mutations": sum(event.get("operation") == "mutation" for event in events),
        "test_outcomes": Counter(
            event.get("normalized", {}).get("exit_status")
            for event in events if event.get("operation") == "test"
        ) or None,
    }


def deduplicate_catalog_findings(findings, events=None):
    """Return one representative finding for each task-local occurrence."""
    result = []
    seen = set()
    for finding in findings:
        candidate_id = finding.get("candidate_id")
        if not candidate_id:
            continue
        identity = _occurrence_key(finding, events)
        if identity in seen:
            continue
        seen.add(identity)
        result.append(finding)
    return result


def habit_summaries(findings, events=None):
    """Aggregate task-local candidate occurrences into concise summaries."""
    grouped = {}
    for finding in findings:
        candidate_id = finding.get("candidate_id")
        if not candidate_id:
            continue
        occurrence = _occurrence_key(finding, events)
        bucket = grouped.setdefault((candidate_id, occurrence), {
            "candidate_id": candidate_id,
            "pattern": finding.get("pattern"),
            "occurrence_count": 0,
            "sessions": set(),
            "episodes": set(),
            "confidence": "none",
            "examples": [],
            "metrics": [],
            "possible_intervention": finding.get("possible_intervention"),
        })
        bucket["occurrence_count"] += 1
        scope = _finding_scope(finding, events)
        if scope and scope[0]:
            bucket["sessions"].add(scope[0])
        if scope and scope[1]:
            bucket["episodes"].add(scope[1])
        bucket["examples"].append({
            "evidence": _unique_sources(finding.get("evidence", []))[:4],
            "command": finding.get("command"),
            "path": finding.get("path") or finding.get("read_path"),
            "progress_signal": finding.get("progress_signal"),
        })
        if finding.get("metrics"):
            bucket["metrics"].append(finding["metrics"])
        bucket["confidence"] = _higher_confidence(bucket["confidence"], finding.get("confidence"))
    summaries = {}
    for (candidate_id, _occurrence), bucket in grouped.items():
        summary = summaries.setdefault(candidate_id, {
            "candidate_id": candidate_id,
            "pattern": bucket["pattern"],
            "occurrence_count": 0,
            "sessions": set(),
            "episodes": set(),
            "confidence": "none",
            "examples": [],
            "metrics": [],
            "possible_intervention": bucket["possible_intervention"],
            "try_next_experiment": bucket["possible_intervention"],
            "intervention_status": "unconfirmed_experiment",
        })
        summary["occurrence_count"] += 1
        summary["sessions"].update(bucket["sessions"])
        summary["episodes"].update(bucket["episodes"])
        summary["examples"].extend(bucket["examples"][:1])
        summary.setdefault('all_evidence', []).extend(
            source for finding in findings
            if finding.get('candidate_id') == candidate_id
            for source in finding.get('evidence', [])
        )
        summary["metrics"].extend(bucket["metrics"])
        summary["confidence"] = _higher_confidence(summary["confidence"], bucket["confidence"])
    output = []
    for summary in summaries.values():
        summary["sessions"] = sorted(summary["sessions"])
        summary["episodes"] = sorted(summary["episodes"])
        summary["examples"] = summary["examples"][:1]
        summary["metrics"] = _merge_summary_metrics(summary["metrics"])
        if events and summary.get('all_evidence'):
            source_keys = {(source.get('filepath'), source.get('line')) for source in summary['all_evidence']}
            summary['metrics'] = transparent_metrics([
                event for event in events
                if (event.get('source', {}).get('filepath'), event.get('source', {}).get('line')) in source_keys
            ])
        summary.pop('all_evidence', None)
        output.append(summary)
    return sorted(output, key=lambda item: (-item["occurrence_count"], item["candidate_id"]))


def _unique_sources(evidence):
    seen = set()
    result = []
    for source in evidence:
        key = (source.get("filepath"), source.get("line"))
        if key in seen:
            continue
        seen.add(key)
        result.append(source)
    return result


def _occurrence_key(finding, events=None):
    scope = _finding_scope(finding, events)
    anchors = finding.get("shared_anchors") or {}
    anchor = (
        finding.get("command"),
        finding.get("read_path"),
        finding.get("path"),
        finding.get("exit_status"),
        finding.get("error_evidence"),
        tuple(sorted((key, _freeze(value)) for key, value in anchors.items())),
    )
    return (finding.get("candidate_id"), scope, anchor)


def _finding_scope(finding, events=None):
    if events:
        by_source = {
            (event.get("source", {}).get("filepath"), event.get("source", {}).get("line")): event
            for event in events
        }
        for source in finding.get("evidence", []):
            event = by_source.get((source.get("filepath"), source.get("line")))
            if event and event.get("_analysis_scope"):
                return event["_analysis_scope"]
    sessions = tuple(finding.get("sessions") or ())
    if sessions:
        return (sessions[0], None)
    episodes = tuple(finding.get("episode_ids") or ())
    return (finding.get("session_id"), episodes[0] if episodes else None)


def _freeze(value):
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _higher_confidence(left, right):
    order = {"none": 0, "low": 1, "medium": 2, "high": 3}
    return right if order.get(right, 0) > order.get(left, 0) else left


def _merge_summary_metrics(metrics):
    if not metrics:
        return {}
    keys = set().union(*(item for item in metrics))
    merged = {}
    for key in sorted(keys):
        values = [item.get(key) for item in metrics if isinstance(item.get(key), (int, float))]
        merged[key] = sum(values) if values else None
    return merged


def _evidence_events(finding, events):
    sources = {(item.get("filepath"), item.get("line")) for item in finding.get("evidence", [])}
    return [event for event in events if (event.get("source", {}).get("filepath"), event.get("source", {}).get("line")) in sources]


def _output_size(event):
    value = event.get("output_size") or event.get("normalized", {}).get("output_size")
    return value if isinstance(value, int) and value >= 0 else 0


def _time(event):
    value = event.get("timestamp")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def review_coverage(analysis, sidecar):
    """Report the milestone review gate without claiming unrecorded verdicts."""
    candidates = analysis["candidate_findings"] if "candidate_findings" in analysis else analysis.get("findings", [])
    candidates = [item for item in candidates if item.get("candidate_id")]
    current_ids = {_review_key(item) for item in candidates}
    reviews = sidecar.get("findings", {}) if isinstance(sidecar, dict) else {}
    reviewed = [review for key, review in reviews.items() if key in current_ids and review.get("verdict") in {"avoidable", "intentional", "inconclusive", "false_positive"}]
    sessions = {session for item in candidates for session in (item.get("sessions") or []) if session}
    return {
        "candidate_count": len(candidates),
        "reviewed_count": len(reviewed),
        "representative_session_count": len(sessions),
        "required_candidates": 20,
        "required_sessions": 10,
        "complete": len(reviewed) >= 20 and len(sessions) >= 10,
    }


def _review_key(finding):
    import hashlib
    import json
    identity = {key: finding.get(key) for key in ("kind", "candidate_id", "command", "path", "read_path", "exit_status", "matching_rule", "evidence", "message_evidence", "episode_ids", "session_id", "parent_agent_id", "agents") if finding.get(key) is not None}
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "finding-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def tune_thresholds(sidecar, *, minimum_verdicts=3):
    """Derive explicit local threshold deltas from reviewed verdicts only."""
    reviews = sidecar.get("findings", {}) if isinstance(sidecar, dict) else {}
    counts = Counter(review.get("verdict") for review in reviews.values())
    if sum(counts.values()) < minimum_verdicts:
        return {"status": "insufficient_evidence", "verdict_counts": dict(counts), "threshold_deltas": {}}
    false_positive = counts.get("false_positive", 0)
    avoidable = counts.get("avoidable", 0)
    intentional = counts.get("intentional", 0)
    delta = 1 if false_positive > avoidable and false_positive >= intentional else 0
    return {
        "status": "derived_from_reviewed_verdicts",
        "verdict_counts": dict(counts),
        "threshold_deltas": {"minimum_independent_signals": delta},
    }


def compute_baselines(events, *, window_days=20):
    """Compute transparent daily counts; mark comparison unavailable without history."""
    dates = sorted({(event.get("timestamp") or "")[:10] for event in events if isinstance(event.get("timestamp"), str)})
    current = dates[-1] if dates else None
    prior = dates[:-1]
    def snapshot(values):
        raw_current = values.get(current, 0) if current else 0
        historical_days = [day for day in prior[-window_days:] if day in values]
        historical = [values[day] for day in historical_days]
        return {
            "current_value": raw_current,
            "baseline_window": {"start": historical_days[0] if historical_days else None, "end": historical_days[-1] if historical_days else None},
            "evidence_available": len(historical) >= 2,
            "sample_size": len(historical),
            "baseline_mean": sum(historical) / len(historical) if len(historical) >= 2 else None,
        }
    user_values = Counter((event.get("timestamp") or "")[:10] for event in events if isinstance(event.get("timestamp"), str))
    repositories = {}
    by_repository = {}
    for event in events:
        path = event.get("normalized", {}).get("path")
        if isinstance(path, list): path = path[0] if path else None
        if not isinstance(path, str): continue
        by_repository.setdefault(path, Counter())[(event.get("timestamp") or "")[:10]] += 1
    repositories = {key: snapshot(value) for key, value in sorted(by_repository.items())}
    return {"user": snapshot(user_values), "repositories": repositories, "window_days": window_days}


def lower_signal_candidates(events, baselines=None):
    """Expose 1e records with explicit limitations; these are not 1d findings."""
    baselines = baselines or compute_baselines(events)
    metrics = transparent_metrics(events)
    records = []
    for candidate_id, (pattern, limitation, status) in LOWER_SIGNAL_RULES.items():
        records.append({
            "catalog_schema": CATALOG_SCHEMA,
            "candidate_id": candidate_id,
            "candidate_status": status,
            "pattern": pattern,
            "evidence_kind": "structured",
            "evidence_available": False,
            "evidence_limitation": limitation,
            "unavailable_conditions": [limitation],
            "required_evidence": [limitation],
            "exclusions": ["similar wording or frequency alone", "missing downstream-use or task context"],
            "derivation": "catalog entry retained as unavailable or signal until the missing context is observed",
            "metrics": metrics,
            "baseline": baselines["user"],
            "possible_intervention": None,
            "confirmation_required": True,
        })
    return records
