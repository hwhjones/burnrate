"""Deterministic local reports and review sidecars for the Codex pilot."""

import hashlib
import json
from collections import Counter
from copy import deepcopy


SIDECAR_SCHEMA = "codex-pilot-sidecar-v1"
REPORT_SCHEMA = "codex-pilot-report-v1"


def new_sidecar(*, provider="codex"):
    """Return an empty, versioned local review sidecar."""
    return {
        "schema_version": SIDECAR_SCHEMA,
        "provider": provider,
        "sessions": {},
        "findings": {},
        "episodes": {},
    }


def record_session(
    sidecar, session_id, *, task_family=None, outcome=None,
    workflow_changed=None, notes=None
):
    """Record user-supplied task context without storing task instructions."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")
    if outcome not in {None, "completed", "abandoned", "failed"}:
        raise ValueError("outcome must be completed, abandoned, failed, or None")
    if workflow_changed not in {None, True, False}:
        raise ValueError("workflow_changed must be true, false, or None")
    sessions = sidecar.setdefault("sessions", {})
    sessions[session_id] = {
        "task_family": task_family,
        "outcome": outcome,
        "workflow_changed": workflow_changed,
        "notes": notes,
    }
    return sidecar


def finding_id(finding):
    """Return a stable ID based on finding evidence, not its display order."""
    identity = {
        key: finding.get(key)
        for key in (
            "kind", "candidate_id", "command", "path", "read_path", "exit_status", "matching_rule",
            "evidence", "message_evidence", "episode_ids", "session_id", "parent_agent_id", "agents",
        )
        if finding.get(key) is not None
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "finding-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def record_finding_review(
    sidecar, finding, *, decision, category=None, correction=None, notes=None,
    verdict=None,
):
    """Record a local confirmation or correction for one finding."""
    if decision not in {"no_change", "change_workflow", "unclear", "confirm", "reject", "correct"}:
        raise ValueError("decision must be no_change, change_workflow, unclear, confirm, reject, or correct")
    if verdict not in {None, "avoidable", "intentional", "inconclusive", "false_positive"}:
        raise ValueError("verdict must be avoidable, intentional, inconclusive, or false_positive")
    key = finding_id(finding)
    sidecar.setdefault("findings", {})[key] = {
        "decision": decision,
        "verdict": verdict,
        "candidate_id": finding.get("candidate_id"),
        "category": category,
        "correction": correction,
        "notes": notes,
    }
    return key


def record_episode_review(sidecar, episode, *, decision, correction=None, notes=None):
    """Record a confirm/reject/correct decision for an inferred boundary."""
    if decision not in {"confirm", "reject", "correct"}:
        raise ValueError("decision must be confirm, reject, or correct")
    identity = {"episode_id": episode.get("episode_id"), "boundary_evidence": episode.get("boundary_evidence")}
    key = "episode-" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    sidecar.setdefault("episodes", {})[key] = {"decision": decision, "correction": correction, "notes": notes}
    return key


def report_document(analysis, sidecar=None, inspection_manifest=None):
    """Build a JSON-serializable report document from analyzer output."""
    raw_findings = deepcopy(analysis.get("findings", []))
    findings = deepcopy(analysis["candidate_findings"] if "candidate_findings" in analysis else raw_findings)
    manifest = inspection_manifest if inspection_manifest is not None else analysis.get("inspection_manifest")
    document = {
        "schema_version": REPORT_SCHEMA,
        "finding_count": len(findings),
        "candidate_count": len(findings),
        "raw_finding_count": len(raw_findings),
        "finding_labels": dict(sorted(Counter(item.get("label") for item in findings).items())),
        "findings": findings,
        "raw_findings": raw_findings,
    }
    if manifest:
        document["inspection_manifest"] = deepcopy(manifest)
    for field in (
        "episodes",
        "boundary_rules",
        "similarity_ladder",
        "active_similarity_rules",
        "baselines",
        "lower_signal_candidates",
        "candidate_findings",
        "candidate_count",
        "habit_summaries",
    ):
        if analysis.get(field) is not None:
            document[field] = deepcopy(analysis[field])
    if sidecar is not None:
        document["sidecar_schema_version"] = sidecar.get("schema_version")
        document["reviews"] = deepcopy(sidecar.get("findings", {}))
        document["episode_reviews"] = deepcopy(sidecar.get("episodes", {}))
    return document


def render_json(analysis, sidecar=None, inspection_manifest=None):
    """Render a stable JSON report string."""
    return json.dumps(
        report_document(analysis, sidecar, inspection_manifest),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    ) + "\n"


def render_markdown(analysis, sidecar=None, inspection_manifest=None):
    """Render a stable, evidence-linked Markdown report."""
    findings = analysis["candidate_findings"] if "candidate_findings" in analysis else analysis.get("findings", [])
    manifest = inspection_manifest if inspection_manifest is not None else analysis.get("inspection_manifest", [])
    reviews = sidecar.get("findings", {}) if sidecar else {}
    lines = [
        "# Codex pilot report",
        "",
        f"Candidate occurrences: {len(findings)}",
        "",
        "This report contains structured execution evidence only. Natural-language",
        "user, agent, reasoning, stdout, and stderr bodies are not included.",
        "",
    ]
    if manifest:
        lines.extend(["Inspection manifest:", ""])
        for item in manifest:
            lines.append(
                f"- `{item.get('filepath')}:{item.get('line')}` "
                f"field `{item.get('field')}` ({item.get('role', 'unknown')})"
            )
        lines.append("")
    if analysis.get("habit_summaries"):
        lines.extend(["## Habit summaries", ""])
        for summary in analysis["habit_summaries"]:
            lines.append(
                f"- `{summary.get('candidate_id')}`: {summary.get('occurrence_count')} "
                f"occurrence(s) across {len(summary.get('sessions', []))} session(s); "
                f"{summary.get('pattern')}"
            )
            if summary.get("try_next_experiment") or summary.get("possible_intervention"):
                experiment = summary.get("try_next_experiment") or summary.get("possible_intervention")
                lines.append(f"  - Qualified experiment (unconfirmed): {experiment}")
        lines.append("")
    if analysis.get("lower_signal_candidates"):
        lines.extend(["## Unavailable or signal-only rules", ""])
        for item in analysis["lower_signal_candidates"]:
            lines.append(
                f"- `{item.get('candidate_id')}`: {item.get('evidence_limitation')}"
            )
        lines.append("")
    if analysis.get("episodes"):
        lines.extend(["## Episode boundaries", ""])
        for episode in analysis["episodes"]:
            source = episode.get("boundary_evidence", [{}])[0]
            lines.append(f"- `{episode.get('episode_id')}`: {', '.join(episode.get('boundary_rules', []))} at `{source.get('filepath')}:{source.get('line')}`")
        lines.append("")
    for index, finding in enumerate(findings, 1):
        key = finding_id(finding)
        review = reviews.get(key, {})
        lines.extend([
            f"## {index}. {finding.get('kind', 'unknown')}",
            "",
            f"- Label: `{finding.get('label', 'unavailable')}`",
            f"- Confidence: `{finding.get('confidence', 'none')}`",
            f"- Rule: {finding.get('confidence_rule', 'No rule supplied.')}",
        ])
        for field in ("candidate_id", "candidate_status", "evidence_kind", "matching_rule", "command", "path", "read_path", "exit_status", "attempts", "tokens_consumed", "progress_signal", "metrics", "baseline", "possible_intervention"):
            if finding.get(field) is not None:
                lines.append(f"- {field}: `{finding[field]}`")
        if review:
            lines.append(f"- Review decision: `{review.get('decision')}`")
            if review.get("verdict"):
                lines.append(f"- User verdict: `{review.get('verdict')}`")
        lines.append("- Evidence:")
        for evidence in finding.get("evidence", []):
            lines.append(f"  - `{evidence.get('filepath')}:{evidence.get('line')}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def suggestion_text(sidecar):
    """Return deterministic suggestion text; never write a target file."""
    suggestions = []
    for key, review in sorted(sidecar.get("findings", {}).items()):
        if review.get("decision") != "change_workflow":
            continue
        if review.get("candidate_id") and review.get("verdict") != "avoidable":
            continue
        category = review.get("category") or "execution pattern"
        notes = review.get("notes") or "Review the supporting evidence before changing workflow guidance."
        suggestions.append(f"- [{category}] {notes} (finding {key})")
    if not suggestions:
        return "No workflow-change suggestions recorded.\n"
    return "Suggested workflow review items:\n\n" + "\n".join(suggestions) + "\n"
