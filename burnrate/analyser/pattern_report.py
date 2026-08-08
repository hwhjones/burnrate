"""Deterministic, concise reports for workflow pattern scan results."""

from __future__ import annotations

import copy
import json
import textwrap
from typing import Any, Iterable

from .pattern_catalog import RULE_CATALOG


SCHEMA_VERSION = 3
DEFAULT_FINDING_LIMIT = 3

_ANSI = {
    "cyan": "\x1b[36m",
    "yellow": "\x1b[33m",
    "green": "\x1b[32m",
    "dim": "\x1b[2m",
    "bold": "\x1b[1m",
    "reset": "\x1b[0m",
}

_SCOPE_LABELS = {
    "direct_occurrences": "occurrences",
    "turn_occurrences": "turn occurrences",
    "affected_sessions": "affected sessions",
    "model_streams": "model streams",
    "growth_runs": "growth runs",
    "temporal_pairs": "temporal pairs",
}


def _value(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _style(value: str, tone: str, enabled: bool) -> str:
    if not enabled:
        return value
    return f"{_ANSI[tone]}{value}{_ANSI['reset']}"


def _diagnostics(scan: Any) -> dict[str, Any]:
    value = _value(scan, "diagnostics", {})
    return dict(value) if isinstance(value, dict) else {}


def _session_count(scan: Any, patterns: list[dict[str, Any]]) -> int:
    sessions = _value(scan, "sessions")
    if isinstance(sessions, (list, tuple)):
        return len(sessions)
    return max((int(item.get("affected_sessions", 0)) for item in patterns), default=0)


def _telemetry_coverage(scan: Any, patterns: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics = _diagnostics(scan)
    sessions = _session_count(scan, patterns)
    return {
        "turn": {
            "sessions": sessions,
            "missing_sessions": int(diagnostics.get("frequency_turn_coverage_missing", 0)),
        },
        "lineage": {
            "sessions": sessions,
            "missing_sessions": int(diagnostics.get("frequency_lineage_coverage_missing", 0)),
        },
        "web": {
            "sessions": sessions,
            "missing_sessions": int(diagnostics.get("frequency_web_coverage_missing", 0)),
        },
        "context": {
            "snapshots": int(diagnostics.get("context_snapshots", 0)),
            "missing_input_snapshots": int(diagnostics.get("context_missing_input", 0)),
            "missing_window_snapshots": int(diagnostics.get("context_missing_window", 0)),
            "cache_unavailable_streams": int(diagnostics.get("context_cache_unavailable", 0)),
            "carry_unavailable_events": int(diagnostics.get("context_carry_unavailable", 0)),
        },
    }


def _coverage_gaps(coverage: dict[str, Any], sessions: int) -> list[str]:
    gaps: list[str] = []
    for name in ("turn", "lineage", "web"):
        missing = coverage[name]["missing_sessions"]
        if missing:
            gaps.append(f"{name}: {missing} session{'s' if missing != 1 else ''}")
    context = coverage["context"]
    if sessions and not context["snapshots"]:
        gaps.append("context: no snapshots")
    elif context["missing_input_snapshots"] or context["missing_window_snapshots"]:
        gaps.append("context: incomplete snapshots")
    if context["cache_unavailable_streams"]:
        gaps.append("cache: unavailable semantics")
    if context["carry_unavailable_events"]:
        gaps.append("carry: incomplete ordering")
    return gaps


def rank_patterns(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copied results in deterministic report display order."""
    ranked: list[dict[str, Any]] = []
    for item in results:
        result = copy.deepcopy(item)
        rule_id = str(result.get("id", ""))
        metadata = RULE_CATALOG.get(rule_id, {})
        result["display_priority"] = int(
            result.get("display_priority", metadata.get("display_priority", 99))
        )
        ranked.append(result)
    return sorted(
        ranked,
        key=lambda item: (
            item["display_priority"],
            -int(item.get("affected_sessions", 0)),
            -int(item.get("count", 0)),
            str(item.get("id", "")),
        ),
    )


def _primary_pattern(patterns: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Choose a broadly supported experiment without creating a score."""
    supported = [
        item for item in patterns
        if int(item.get("affected_sessions", 0)) > 1 or int(item.get("count", 0)) > 1
    ]
    if supported:
        return min(
            supported,
            key=lambda item: (
                -int(item.get("affected_sessions", 0)),
                int(item.get("display_priority", 99)),
                -int(item.get("count", 0)),
                str(item.get("id", "")),
            ),
        ), "affected_sessions, display_priority, count, rule_id"
    return (patterns[0] if patterns else None), "display_priority, affected_sessions, count, rule_id"


def _build_insights(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group raw rules into a few interpretable, deterministic stories."""
    by_id = {str(item.get("id")): item for item in patterns}
    insights: list[dict[str, Any]] = []
    output = by_id.get("R-OUT-01")
    carry = by_id.get("R-CARRY-01")
    growth = by_id.get("R-CTX-02")
    pressure = by_id.get("R-CTX-01")
    reads = by_id.get("R-READ-01")

    if output and carry:
        output_sessions = int(output.get("affected_sessions", 0))
        carry_sessions = int(carry.get("affected_sessions", 0))
        ratio = round((carry_sessions / output_sessions) * 100) if output_sessions else 0
        output_threshold = int(output.get("threshold", RULE_CATALOG["R-OUT-01"].get("threshold", 0)))
        carry_threshold = int(carry.get("threshold", RULE_CATALOG["R-CARRY-01"].get("threshold", 0)))
        insights.append({
            "id": "I-OUTPUT-CONTEXT-01",
            "name": "Large outputs often expanded later context",
            "display_priority": 1,
            "affected_sessions": carry_sessions,
            "count": int(carry.get("count", 0)),
            "evidence": (
                f"{int(output.get('count', 0)):,} outputs over {output_threshold:,} characters in "
                f"{output_sessions} sessions; {carry_sessions}/{output_sessions} "
                f"sessions ({ratio}%) also showed a later input increase over "
                f"{carry_threshold:,} tokens ({int(carry.get('count', 0)):,} temporal pairs)."
            ),
            "try_next_experiment": "Cap reads and command output with a range, filter, or line limit.",
            "examples": (carry.get("examples") or output.get("examples") or [])[:1],
            "source_rule_ids": ["R-OUT-01", "R-CARRY-01"],
            "thresholds": {"output_characters": output_threshold, "input_increase_tokens": carry_threshold},
        })

    if growth:
        growth_sessions = int(growth.get("affected_sessions", 0))
        growth_run_threshold = int(growth.get("threshold", RULE_CATALOG["R-CTX-02"].get("threshold", 0)))
        growth_step_threshold = int(growth.get("secondary_threshold", RULE_CATALOG["R-CTX-02"].get("secondary_threshold", 0)))
        evidence = (
            f"{int(growth.get('count', 0)):,} sustained growth runs across "
            f"{growth_sessions} sessions, requiring {growth_run_threshold} consecutive "
            f"steps of at least {growth_step_threshold:,} tokens."
        )
        pressure_threshold = None
        if pressure:
            pressure_threshold = float(pressure.get("threshold", RULE_CATALOG["R-CTX-01"].get("threshold", 0)))
            evidence += (
                f" Separately, {int(pressure.get('affected_sessions', 0))} sessions "
                f"reached at least {pressure_threshold:.0%} of the reported context window."
            )
        insights.append({
            "id": "I-CONTEXT-GROWTH-01",
            "name": "Context grew steadily during sessions",
            "display_priority": 2,
            "affected_sessions": growth_sessions,
            "count": int(growth.get("count", 0)),
            "evidence": evidence,
            "try_next_experiment": "Start a fresh context at a stable task boundary and carry forward only the current state.",
            "examples": (growth.get("examples") or [])[:1],
            "source_rule_ids": ["R-CTX-02"] + (["R-CTX-01"] if pressure else []),
            "thresholds": {
                "growth_run_length": growth_run_threshold,
                "growth_step_tokens": growth_step_threshold,
                **({"context_utilization": pressure_threshold} if pressure_threshold is not None else {}),
            },
        })

    if reads:
        read_sessions = int(reads.get("affected_sessions", 0))
        insights.append({
            "id": "I-REPEATED-READS-01",
            "name": "Repeated reads were concentrated in a few sessions",
            "display_priority": 3,
            "affected_sessions": read_sessions,
            "count": int(reads.get("count", 0)),
            "evidence": f"{int(reads.get('count', 0)):,} repeated reads across {read_sessions} sessions.",
            "try_next_experiment": "Reference the earlier read while it remains current.",
            "examples": (reads.get("examples") or [])[:1],
            "source_rule_ids": ["R-READ-01"],
        })

    if not insights:
        for item in patterns:
            insights.append({
                "id": f"I-{item.get('id', 'UNKNOWN')}",
                "name": item.get("name", "Observed signal"),
                "display_priority": int(item.get("display_priority", 99)),
                "affected_sessions": int(item.get("affected_sessions", 0)),
                "count": int(item.get("count", 0)),
                "evidence": _scope_text(item),
                "try_next_experiment": _experiment(item),
                "examples": (item.get("examples") or [])[:1],
                "source_rule_ids": [item.get("id")],
            })
    return sorted(
        insights,
        key=lambda item: (
            int(item.get("display_priority", 99)),
            -int(item.get("affected_sessions", 0)),
            -int(item.get("count", 0)),
            str(item.get("id", "")),
        ),
    )


def _scope_text(item: dict[str, Any]) -> str:
    count = int(item.get("count", 0))
    scope = str(item.get("count_scope", "occurrences"))
    label = _SCOPE_LABELS.get(scope, scope.replace("_", " "))
    affected = int(item.get("affected_sessions", 0))
    if scope == "affected_sessions":
        return f"{count} affected session{'s' if count != 1 else ''}"
    if count == 1 and label.endswith("s"):
        label = label[:-1]
    return f"{count} {label} · {affected} affected session{'s' if affected != 1 else ''}"


def _experiment(item: dict[str, Any]) -> str | None:
    value = item.get("try_next_experiment")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _native_scope_text(item: dict[str, Any]) -> str:
    count = int(item.get("count", 0))
    scope = str(item.get("count_scope", "occurrences"))
    label = _SCOPE_LABELS.get(scope, scope.replace("_", " "))
    if scope == "affected_sessions":
        return f"{count} affected session{'s' if count != 1 else ''}"
    if count == 1 and label.endswith("s"):
        label = label[:-1]
    return f"{count} {label}"


def _threshold_text(item: dict[str, Any]) -> str | None:
    threshold = item.get("threshold")
    if threshold is None:
        return None
    unit = str(item.get("unit", ""))
    if unit == "ratio":
        return f"threshold {float(threshold):.0%} context utilization"
    if unit == "tokens_per_snapshot":
        secondary = item.get("secondary_threshold")
        suffix = f" and +{int(secondary):,} tokens per step" if secondary is not None else ""
        return f"threshold {int(threshold)} consecutive snapshots{suffix}"
    labels = {
        "work_tokens": "work tokens",
        "tokens": "tokens",
        "characters": "output characters",
        "seconds": "seconds",
        "spawns": "spawns",
        "calls": "calls per turn",
    }
    label = labels.get(unit, unit.replace("_", " ") or "measured value")
    return f"threshold {int(threshold):,} {label}"


def _example_text(item: dict[str, Any]) -> str | None:
    examples = item.get("examples") or []
    if not examples:
        return None
    example = examples[0]
    filepath = str(example.get("filepath", "unknown source"))
    if len(filepath) > 64:
        filepath = ".../" + filepath.replace("\\", "/").rsplit("/", 1)[-1]
    source = f"{filepath}:{example.get('line', '?')}"
    fields = []
    for key, label in (
        ("tokens", "observed"), ("characters", "observed"),
        ("duration_seconds", "observed"), ("measured_value", "measured"),
        ("count", "observed"), ("target", "target"), ("command", "command"),
    ):
        value = example.get(key)
        if value is None:
            continue
        if key == "measured_value" and item.get("unit") == "ratio":
            value = f"{float(value):.0%}"
        elif isinstance(value, (int, float)):
            value = f"{value:,}"
        text = str(value).replace("\r", " ").replace("\n", " ").strip()
        if len(text) > 72:
            text = text[:69] + "..."
        fields.append(f"{label} {text}")
        if len(fields) == 1:
            break
    if "model_id" in example:
        fields.append(f"model {example.get('model_id') or 'unknown'}")
    return f"Example: {source}" + (" · " + " · ".join(fields) if fields else "")


def _signal_detail_lines(item: dict[str, Any]) -> list[str]:
    details = [f"{_scope_text(item)}"]
    threshold = _threshold_text(item)
    if threshold:
        details.append(threshold)
    example = _example_text(item)
    if example:
        details.append(example)
    return details


def _insight_detail_lines(item: dict[str, Any]) -> list[str]:
    details = [item.get("evidence", "Observed signal.")]
    example = _example_text(item)
    if example:
        details.append(example)
    return details


def _detail_lines(item: dict[str, Any]) -> list[str]:
    details = [
        f"  {item['id']}: {item.get('explanation', '')}",
        f"  Scope: {item.get('count_scope', 'occurrences')} · threshold: {item.get('threshold', 'n/a')}",
    ]
    if item.get("secondary_threshold") is not None:
        details.append(f"  Secondary threshold: {item['secondary_threshold']}")
    if item.get("unit"):
        details.append(f"  Unit: {item['unit']}")
    if item.get("telemetry_required"):
        details.append("  Telemetry: " + ", ".join(item["telemetry_required"]))
    for example in item.get("examples", [])[:3]:
        filepath = example.get("filepath", "unknown source")
        line = example.get("line", "?")
        scope = ""
        if "model_id" in example:
            scope = f" [{example.get('model_id')}, stream {example.get('stream_epoch', 0)}]"
        details.append(f"  Example: {filepath}:{line}{scope}")
    return details


def build_report(results: Iterable[dict[str, Any]], scan: Any = None,
                 window_days: int | None = None, explain_command: str | None = None,
                 rerun_command: str | None = None) -> dict[str, Any]:
    """Build the complete report object shared by text and JSON renderers."""
    patterns = rank_patterns(results)
    sessions = _session_count(scan, patterns)
    coverage = _telemetry_coverage(scan, patterns)
    insights = _build_insights(patterns)
    primary = insights[0] if insights else None
    return {
        "schema_version": SCHEMA_VERSION,
        "window_days": window_days,
        "scan": {
            "status": _value(scan, "status", "complete"),
            "sessions": sessions,
            "files_scanned": int(_value(scan, "files_scanned", 0) or 0),
            "malformed_records": int(_value(scan, "malformed_records", 0) or 0),
            "telemetry_coverage": coverage,
            "diagnostics": _diagnostics(scan),
        },
        "totals": {
            "rule_matches": sum(int(item.get("count", 0)) for item in patterns),
            "patterns": len(patterns),
        },
        "presentation": {
            "primary_pattern_id": primary.get("source_rule_ids", [None])[0] if primary else None,
            "primary_insight_id": primary.get("id") if primary else None,
            "selection_basis": "insight_priority, affected_sessions, count, insight_id" if primary else None,
            "explain_command": explain_command or "burnrate patterns --explain",
            "rerun_command": rerun_command or "burnrate patterns --days 7",
        },
        "insights": insights,
        "patterns": patterns,
    }


def render_json(results: Iterable[dict[str, Any]], scan: Any = None,
                window_days: int | None = None, explain_command: str | None = None,
                rerun_command: str | None = None) -> str:
    """Render the complete report as deterministic JSON."""
    report = build_report(results, scan=scan, window_days=window_days,
                          explain_command=explain_command, rerun_command=rerun_command)
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_text(results: Iterable[dict[str, Any]], scan: Any = None,
                window_days: int | None = None, explain: bool = False,
                finding_limit: int = DEFAULT_FINDING_LIMIT,
                explain_command: str | None = None,
                rerun_command: str | None = None, color: bool = False) -> str:
    """Render a concise report, or the complete explain view."""
    report = build_report(results, scan=scan, window_days=window_days,
                          explain_command=explain_command, rerun_command=rerun_command)
    patterns = report["patterns"]
    insights = report["insights"]
    primary = insights[0] if insights else None
    displayed = patterns if explain else insights[:max(0, finding_limit)]
    sessions = report["scan"]["sessions"]
    days = f"last {window_days} days" if window_days is not None else "selected window"
    files = int(report["scan"].get("files_scanned", 0))
    period = f"{window_days} days" if window_days is not None else "selected window"
    lines = [
        _style(f"BurnRate | {period} workflow briefing", "cyan", color),
        _style(f"{sessions} sessions | {files} files | {len(patterns)} raw signals", "dim", color),
        "",
    ]
    if report["scan"]["status"] == "invalid":
        lines.append("Pattern scan unavailable: the log path is invalid or unreadable.")
    elif not patterns:
        lines.append("No qualifying patterns were observed.")
    else:
        if not explain and primary:
            lines.append(_style("Top 3 signals", "bold", color))
            for index, item in enumerate(displayed, start=1):
                lines.extend(["", "+" + "-" * 62 + "+", f"| {index}. {_style(item['name'], 'cyan', color)}"])
                for detail in _insight_detail_lines(item):
                    wrapped = textwrap.wrap(detail, width=58) or [""]
                    for part in wrapped:
                        styled = _style(part, "dim", color) if detail.startswith("Example:") else part
                        lines.append(f"|   {styled}")
                lines.extend(["|", f"|   {_style('Try:', 'green', color)}"])
                for part in textwrap.wrap(item.get("try_next_experiment") or "Inspect the source example.", width=58):
                    lines.append(f"|   {part}")
                lines.append("+" + "-" * 62 + "+")
            lines.extend(["", _style("Check again:", "green", color), report["presentation"]["rerun_command"]])
        for item in displayed:
            if explain:
                lines.append(_style(item["name"], "cyan", color))
                lines.extend([f"  {line}" for line in _signal_detail_lines(item)])
                lines.extend(_detail_lines(item))
        if not explain:
            remaining = max(0, len(insights) - len(displayed)) + max(0, len(patterns) - len(insights))
            if remaining:
                lines.extend(["", _style(f"{remaining} more raw signals: {report['presentation']['explain_command']}", "dim", color)])
        if explain:
            for item in displayed:
                experiment = _experiment(item)
                if experiment:
                    lines.extend(["", f"Experiment for {item['name']}:", experiment])

    gaps = _coverage_gaps(report["scan"]["telemetry_coverage"], sessions)
    if gaps:
        lines.extend(["", _style("Coverage: " + "; ".join(gaps) + ".", "yellow", color)])
    lines.extend(["", _style("Observations only - not measured waste; this does not measure code correctness or successful verification.", "dim", color)])
    if not explain and patterns:
        lines.extend([_style(f"{report['presentation']['explain_command']} for raw rule evidence.", "dim", color)])
    return "\n".join(lines) + "\n"


__all__ = ["SCHEMA_VERSION", "build_report", "rank_patterns", "render_json", "render_text"]
