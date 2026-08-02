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
            "kind", "command", "path", "read_path", "exit_status",
            "evidence", "session_id", "parent_agent_id", "agents",
        )
        if finding.get(key) is not None
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return "finding-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def record_finding_review(
    sidecar, finding, *, decision, category=None, correction=None, notes=None
):
    """Record a local confirmation or correction for one finding."""
    if decision not in {"no_change", "change_workflow", "unclear"}:
        raise ValueError("decision must be no_change, change_workflow, or unclear")
    key = finding_id(finding)
    sidecar.setdefault("findings", {})[key] = {
        "decision": decision,
        "category": category,
        "correction": correction,
        "notes": notes,
    }
    return key


def report_document(analysis, sidecar=None):
    """Build a JSON-serializable report document from analyzer output."""
    findings = deepcopy(analysis.get("findings", []))
    document = {
        "schema_version": REPORT_SCHEMA,
        "finding_count": len(findings),
        "finding_labels": dict(sorted(Counter(item.get("label") for item in findings).items())),
        "findings": findings,
    }
    if sidecar is not None:
        document["sidecar_schema_version"] = sidecar.get("schema_version")
        document["reviews"] = deepcopy(sidecar.get("findings", {}))
    return document


def render_json(analysis, sidecar=None):
    """Render a stable JSON report string."""
    return json.dumps(
        report_document(analysis, sidecar),
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    ) + "\n"


def render_markdown(analysis, sidecar=None):
    """Render a stable, evidence-linked Markdown report."""
    findings = analysis.get("findings", [])
    reviews = sidecar.get("findings", {}) if sidecar else {}
    lines = [
        "# Codex pilot report",
        "",
        f"Findings: {len(findings)}",
        "",
        "This report contains structured execution evidence only. Natural-language",
        "user, agent, reasoning, stdout, and stderr bodies are not included.",
        "",
    ]
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
        for field in ("command", "path", "read_path", "exit_status", "attempts", "tokens_consumed"):
            if finding.get(field) is not None:
                lines.append(f"- {field}: `{finding[field]}`")
        if review:
            lines.append(f"- Review decision: `{review.get('decision')}`")
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
        category = review.get("category") or "execution pattern"
        notes = review.get("notes") or "Review the supporting evidence before changing workflow guidance."
        suggestions.append(f"- [{category}] {notes} (finding {key})")
    if not suggestions:
        return "No workflow-change suggestions recorded.\n"
    return "Suggested workflow review items:\n\n" + "\n".join(suggestions) + "\n"
