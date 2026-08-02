"""Content-to-execution correlation for opted-in normalized trace timelines.

This module deliberately returns source locations and structured anchors, never
the message bodies it inspected.  Its rules are deterministic and exposed as
data so a reviewer can correct either an episode boundary or a candidate.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
import re


IDLE_GAP_SECONDS = 15 * 60

BOUNDARY_RULES = {
    "first_event": "The first observable event starts an episode.",
    "explicit_user_request": "A selected, informative user message starts a new requested-work episode.",
    "agent_handoff": "A changed normalized agent identity starts a new ownership episode.",
    "idle_gap": "A timestamp gap of at least 900 seconds starts a new episode.",
    "repository_or_workdir_change": "A changed observed repository/workdir anchor starts a new context episode.",
    "terminal_mutation": "A successful mutation starts a post-change verification episode.",
    "terminal_test": "A completed test output starts a post-test episode.",
}

SIMILARITY_LADDER = (
    "exact_normalized_fingerprint",
    "term_containment",
    "identifier_aware_token_overlap",
    "character_ngrams",
    "local_bm25",
)
ACTIVE_SIMILARITY_RULES = {
    "exact_normalized_fingerprint",
    "identifier_aware_token_overlap",
}

_IDENTIFIER = re.compile(r"(?:[a-z_]+[0-9][a-z0-9_./:-]*|[a-z0-9_./:-]*[_.:/-][a-z0-9_./:-]*)")


def segment_episodes(events, *, idle_gap_seconds=IDLE_GAP_SECONDS):
    """Split one normalized event stream into inspectable, source-linked episodes."""
    timeline = sorted(events, key=_timeline_key)
    episodes = []
    current = None
    previous = None
    for event in timeline:
        reasons = _boundary_reasons(previous, event, idle_gap_seconds)
        if current is None or reasons:
            if current is not None:
                current["end_evidence"] = _source(previous)
            current = {
                "episode_id": f"episode-{len(episodes) + 1}",
                "boundary_rules": reasons or ["first_event"],
                "boundary_evidence": [_source(event)],
                "event_evidence": [],
                "request_evidence": [],
                "agent_lineage": [],
                "progress_signals": [],
            }
            episodes.append(current)
        current["event_evidence"].append(_source(event))
        if event.get("event_type") == "user_message" and _informative(event):
            current["request_evidence"].append(_source(event))
        lineage = (event.get("normalized", {}).get("agent_id"), event.get("normalized", {}).get("parent_agent_id"))
        if any(lineage) and lineage not in current["agent_lineage"]:
            current["agent_lineage"].append(lineage)
        signal = _progress_signal(event)
        if signal and signal not in current["progress_signals"]:
            current["progress_signals"].append(signal)
        previous = event
    for episode in episodes:
        episode["event_count"] = len(episode["event_evidence"])
        episode["agent_lineage"] = [
            {"agent_id": agent, "parent_agent_id": parent}
            for agent, parent in episode["agent_lineage"]
        ]
        episode["progress_signals"] = sorted(episode["progress_signals"])
    return episodes


def correlate_messages(events, episodes=None):
    """Return message pairs and evidence-backed candidates, with explicit exclusions."""
    timeline = sorted(events, key=_timeline_key)
    episodes = episodes or segment_episodes(timeline)
    membership = _membership(episodes)
    messages = [event for event in timeline if event.get("event_type") in {"user_message", "agent_message"} and _informative(event)]
    episode_events = defaultdict(list)
    for event in timeline:
        episode_events[membership.get(_source_key(event))].append(event)
    matches = []
    bm25_context = _bm25_context(messages)
    for first, second in _message_pairs(messages):
        rule, score = similarity_rule(first, second, messages, bm25_context)
        if rule is None:
            continue
        first_episode = membership.get(_source_key(first))
        second_episode = membership.get(_source_key(second))
        anchors = _shared_execution_anchors(
            episode_events[first_episode], episode_events[second_episode],
        )
        matches.append({
            "matching_rule": rule,
            "similarity_score": score,
            "message_evidence": [_source(first), _source(second)],
            "episode_ids": [first_episode, second_episode],
            "shared_anchors": anchors,
            "execution_evidence_present": bool(anchors),
        })
    candidates = _high_precision_candidates(timeline, episodes, membership, matches, episode_events)
    return {
        "similarity_ladder": list(SIMILARITY_LADDER),
        "active_similarity_rules": sorted(ACTIVE_SIMILARITY_RULES),
        "message_matches": matches,
        "candidates": candidates,
    }


def _message_pairs(messages):
    """Yield bounded, same-session lexical candidates in trace order.

    Each message compares against the four nearest earlier messages for each
    term and fingerprint. Three shared terms are required for non-exact pairs.
    This keeps a long local history reviewable without a quadratic sweep while
    retaining the local-repeat evidence required by the candidate rules.
    """
    by_session = defaultdict(list)
    for index, message in enumerate(messages):
        by_session[message.get("normalized", {}).get("session_id", "<unknown>")].append((index, message))
    for entries in by_session.values():
        fingerprints = defaultdict(list)
        terms = defaultdict(list)
        lookup = dict(entries)
        for index, message in entries:
            candidates = Counter()
            for previous in fingerprints[message["normalized"]["content_fingerprint"]][-4:]:
                candidates[previous] = 3_000  # Exact fingerprints always qualify.
            for term in _comparison_terms(message):
                for previous in terms[term][-4:]:
                    candidates[previous] += 1
            for previous, shared_count in sorted(candidates.items()):
                if shared_count >= 3:
                    yield lookup[previous], message
            fingerprints[message["normalized"]["content_fingerprint"]].append(index)
            for term in _comparison_terms(message):
                terms[term].append(index)


def similarity_rule(first, second, corpus, bm25_context=None):
    """Apply the documented similarity ladder, returning the first passing rule."""
    left, right = _terms(first), _terms(second)
    if first.get("normalized", {}).get("content_fingerprint") == second.get("normalized", {}).get("content_fingerprint"):
        return "exact_normalized_fingerprint", 1.0
    intersection = left & right
    if min(len(left), len(right)) >= 4 and (left <= right or right <= left):
        return "term_containment", round(min(len(left), len(right)) / max(len(left), len(right)), 3)
    identifiers = {term for term in intersection if _IDENTIFIER.fullmatch(term)}
    if len(identifiers) >= 2 and len(intersection) >= 3:
        return "identifier_aware_token_overlap", round(len(intersection) / len(left | right), 3)
    ngram = _ngram_similarity(left, right)
    if ngram >= 0.82:
        return "character_ngrams", ngram
    bm25 = _bm25_similarity(left, right, corpus, bm25_context)
    if bm25 >= 0.72:
        return "local_bm25", bm25
    return None, 0.0


def _boundary_reasons(previous, event, idle_gap_seconds):
    if previous is None:
        return ["first_event"]
    reasons = []
    if event.get("event_type") == "user_message" and _informative(event):
        reasons.append("explicit_user_request")
    if _agent(previous) and _agent(event) and _agent(previous) != _agent(event):
        reasons.append("agent_handoff")
    before, after = _parsed_time(previous), _parsed_time(event)
    if before and after and (after - before).total_seconds() >= idle_gap_seconds:
        reasons.append("idle_gap")
    if _context_anchor(previous) and _context_anchor(event) and not _contexts_related(_context_anchor(previous), _context_anchor(event)):
        reasons.append("repository_or_workdir_change")
    if _is_terminal(previous, "mutation"):
        reasons.append("terminal_mutation")
    if _is_terminal(previous, "test"):
        reasons.append("terminal_test")
    return reasons


def _high_precision_candidates(timeline, episodes, membership, matches, episode_events):
    candidates = []
    for match in matches:
        if match["matching_rule"] not in ACTIVE_SIMILARITY_RULES:
            continue  # Experimental similarity is diagnostic-only.
        if not match["execution_evidence_present"]:
            continue  # Similar wording alone is never a candidate.
        first_id, second_id = match["episode_ids"]
        related = episode_events[second_id]
        anchors = match["shared_anchors"]
        mutation = any(_progress_signal(event) == "successful_mutation" for event in related)
        test_success = any(_progress_signal(event) == "successful_test" for event in related)
        repeated_reads = _repeated_investigation(related)
        repeated_failure = _repeated_failure(related)
        if repeated_reads and not mutation and not test_success:
            candidates.append(_candidate("repeated_investigation_without_progress", match, related,
                "Repeated read/discovery evidence and matching informative messages; no successful mutation or test was observed.",
                ["requires informative message match", "requires shared execution anchor", "excluded when mutation or successful test is observed"],
                "no_progress_observed"))
        if repeated_failure and not mutation and not test_success:
            candidates.append(_candidate("ineffective_retry_loop", match, related,
                "Repeated normalized failure evidence and matching informative messages; no successful mutation or test was observed.",
                ["requires repeated command and failure fingerprint", "requires informative message match", "excluded when mutation or successful test is observed"],
                "no_progress_observed"))
    candidates.extend(_semantic_subagent_candidates(
        [match for match in matches if match['matching_rule'] in ACTIVE_SIMILARITY_RULES],
        episode_events,
    ))
    return _dedupe(candidates)


def _semantic_subagent_candidates(matches, episode_events):
    candidates = []
    for match in matches:
        first_id, second_id = match["episode_ids"]
        if not first_id or not second_id or first_id == second_id or not match["shared_anchors"]:
            continue
        left = episode_events[first_id]
        right = episode_events[second_id]
        left_lineage, right_lineage = _lineage(left), _lineage(right)
        if not left_lineage or not right_lineage or left_lineage[0] == right_lineage[0] or left_lineage[1] != right_lineage[1]:
            continue
        if any(_progress_signal(event) == "successful_mutation" for event in left + right):
            continue
        candidates.append(_candidate("probable_semantic_subagent_duplication", match, left + right,
            "Sibling agents have an informative semantic match, shared execution anchors, and no observed differentiating successful mutation.",
            ["requires sibling lineage", "requires informative semantic match", "requires shared execution anchor", "excluded when a differentiating successful mutation is observed"],
            "no_differentiating_mutation_observed"))
    return candidates


def _candidate(kind, match, events, rule, exclusions, progress):
    return {
        "kind": kind, "label": "heuristic", "confidence": "high", "evidence_kind": "combined",
        "confidence_rule": rule, "matching_rule": match["matching_rule"], "shared_anchors": match["shared_anchors"],
        "message_evidence": match["message_evidence"], "evidence": [_source(event) for event in events],
        "exclusions": exclusions, "progress_signal": progress,
        "episode_ids": match["episode_ids"],
    }


def _informative(event):
    normalized = event.get("normalized", {})
    return bool(normalized.get("content_fingerprint")) and not normalized.get("content_excluded_reason") and normalized.get("content_token_count", 0) >= 4


def _terms(event): return set(event.get("normalized", {}).get("content_terms") or [])
def _comparison_terms(event):
    terms = _terms(event)
    identifiers = sorted(term for term in terms if _IDENTIFIER.fullmatch(term))
    lexical = sorted((term for term in terms if term not in identifiers), key=lambda term: (-len(term), term))
    return set((identifiers + lexical)[:64])
def _agent(event): return event.get("normalized", {}).get("agent_id")
def _source(event): return event.get("source", {})
def _source_key(event):
    source = _source(event); return (source.get("filepath"), source.get("line"))
def _context_anchor(event):
    value = event.get("normalized", {}).get("path")
    if isinstance(value, list): value = value[0] if value else None
    return value
def _contexts_related(left, right):
    left, right = left.rstrip("/"), right.rstrip("/")
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")
def _lineage(events):
    for event in events:
        agent, parent = _agent(event), event.get("normalized", {}).get("parent_agent_id")
        if agent and parent: return agent, parent
    return None
def _progress_signal(event):
    normalized = event.get("normalized", {})
    if event.get("operation") == "mutation" and normalized.get("mutation_status") == "succeeded": return "successful_mutation"
    if event.get("operation") == "test" and normalized.get("exit_status") == "success": return "successful_test"
    return None
def _is_terminal(event, operation): return event.get("operation") == operation and (_progress_signal(event) or operation == "test" and event.get("event_type") == "tool_output")
def _parsed_time(event):
    value = event.get("timestamp")
    if not isinstance(value, str): return None
    try: result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
def _timeline_key(event):
    value = _parsed_time(event); source = _source(event)
    return (value is not None, value or datetime.min.replace(tzinfo=timezone.utc), source.get("filepath", ""), source.get("line", 0))
def _membership(episodes):
    return { (item.get("filepath"), item.get("line")): episode["episode_id"] for episode in episodes for item in episode["event_evidence"] }
def _events_for_episode(events, episode_id, membership): return [event for event in events if membership.get(_source_key(event)) == episode_id]
def _episode_sources(events, episode):
    start = episode["boundary_evidence"][0]; end = episode.get("end_evidence")
    capture = False; result = []
    for event in sorted(events, key=_timeline_key):
        if _source(event) == start: capture = True
        if capture: result.append(_source(event))
        if capture and end and _source(event) == end: break
    return result
def _shared_execution_anchors(left, right):
    def values(events, field):
        result = set()
        for event in events:
            value = event.get("normalized", {}).get(field)
            if isinstance(value, str): result.add(value)
            elif isinstance(value, list): result.update(item for item in value if isinstance(item, str))
        return result
    output = {}
    for field in ("command", "path", "read_path", "error_fingerprint"):
        shared = sorted(values(left, field) & values(right, field))
        if shared: output[field] = shared
    return output
def _repeated_investigation(events):
    seen = set()
    for event in events:
        if event.get("operation") not in {"read", "discovery"}:
            continue
        normalized = event.get("normalized", {})
        target = normalized.get("read_path") or normalized.get("command")
        key = (event.get("operation"), target, _path_key(normalized.get("path")))
        if target:
            if key in seen:
                return True
            seen.add(key)
    return False

def _path_key(value):
    return tuple(value) if isinstance(value, list) else value

def _repeated_failure(events):
    seen = set()
    for event in events:
        normal = event.get("normalized", {})
        key = (normal.get("command"), normal.get("error_fingerprint") or normal.get("error_text"), normal.get("exit_status"))
        if key[0] and key[1] and isinstance(key[2], str) and key[2].startswith("failure:"):
            if key in seen: return True
            seen.add(key)
    return False
def _ngram_similarity(left, right):
    def grams(words):
        return {" ".join(sorted(words))[index:index + 3] for index in range(max(0, len(" ".join(sorted(words))) - 2))}
    a, b = grams(left), grams(right)
    return round(len(a & b) / len(a | b), 3) if a and b else 0.0
def _bm25_context(corpus):
    return len(corpus), Counter(term for event in corpus for term in _terms(event))
def _bm25_similarity(left, right, corpus, context=None):
    total, count = context or _bm25_context(corpus)
    shared = left & right
    if len(shared) < 3: return 0.0
    score = sum(math.log((total + 1) / (count[term] + 1)) + 1 for term in shared)
    maximum = sum(math.log((total + 1) / 1) + 1 for term in left | right)
    return round(score / maximum, 3) if maximum else 0.0
def _dedupe(items):
    result, seen = [], set()
    for item in items:
        key = (item["kind"], tuple(item["episode_ids"]), tuple((e.get("filepath"), e.get("line")) for e in item["message_evidence"]))
        if key not in seen: result.append(item); seen.add(key)
    return result
