# BurnRate Workflow Pattern Scan Implementation Plan

## Purpose

This is the authoritative implementation plan for the next BurnRate feature.
Product direction and later milestones live in [ROADMAP.md](ROADMAP.md).
Completed historical work is not repeated here.

Start from `main` at `9c83815`. Do not merge or copy the experimental
`burnrate/traces/` implementation. Preserve the existing usage, cost, parser,
packaging, and CLI behavior unless a PR below explicitly changes it.

The feature has one job:

> Read local Codex logs, count a small number of transparent workflow patterns,
> rank them, and show one qualified experiment for each pattern.

It is a workflow pattern scanner, not a habit detector and not a waste-scoring
system.

## User contract

The completed vertical slice provides:

```console
burnrate --patterns --parser codex --days 20
```

Default output stays short:

```text
BurnRate workflow pattern scan - last 20 days
Sessions: 42  |  pattern occurrences: 38

Exploration pile-ups                x27
Repeated file reads                 x10
Ineffective retries                  x1

Try next experiment:
Narrow the exploration scope before starting another sweep.

These are deterministic observations and frequency signals, not measured waste.
Use --explain to see thresholds and source examples.
```

Terminology is fixed:

- an **occurrence** is one detected event or sequence;
- a **pattern** aggregates occurrences over the selected window;
- a **frequency signal** is a threshold count that requires interpretation;
- the release does not label anything a habit or confirmed waste.

## Initial rule set

| ID | Pattern | Deterministic rule | Classification |
| --- | --- | --- | --- |
| `R-READ-01` | Repeated file read | Same normalized file is read again in one session | observation |
| `R-RETRY-01` | Ineffective retry | Same normalized command and failure fingerprint recur consecutively | observation |
| `R-TEST-01` | Test churn | Same test command recurs without an intervening successful mutation | observation |
| `R-EXP-01` | Exploration pile-up | At least four read or discovery calls occur in one turn | frequency signal |
| `R-SESSION-01` | Long session | Observed session duration exceeds 35 minutes | frequency signal |
| `R-TOKEN-01` | Token pile-up | Session work tokens exceed 50,000 | frequency signal |
| `R-OUT-01` | Large tool output | One tool result exceeds 8,000 characters | frequency signal |
| `R-SUBAGENT-01` | Subagent-heavy session | At least six subagent spawns occur in one session | frequency signal |
| `R-WEB-01` | Web-heavy session | Count observed web search/fetch calls | frequency signal |

Missing required telemetry suppresses only the affected rule. It does not emit
an unavailable finding.

## Architecture constraints

Add at most three production modules:

```text
burnrate/
  analyser/
    patterns.py        JSONL reader, session accumulator, detectors
    pattern_catalog.py rule names, thresholds, explanations, experiments
  pattern_report.py    deterministic text and JSON rendering
  main.py              existing CLI plus opt-in pattern routing
```

Use one result shape throughout detection, aggregation, JSON, and text output:

```python
{
    "id": "R-READ-01",
    "name": "Repeated file reads",
    "classification": "observation",
    "count": 10,
    "affected_sessions": 6,
    "explanation": "The same normalized file was read more than once.",
    "try_next_experiment": "Reference the earlier read when it remains current.",
    "examples": [
        {"filepath": "session.jsonl", "line": 123, "target": "src/app.py"}
    ],
}
```

Keep at most three source-linked examples per pattern. Never retain or print
message bodies or tool-output bodies.

Aggregate within each session before combining results. Never subtract or
compare cumulative token counters belonging to different sessions.

## Pull request sequence

Implement the feature in five sequential PRs. Create each branch from the
updated `main` after the preceding PR has merged.

| PR | Branch | User-visible outcome | Depends on |
| --- | --- | --- | --- |
| 1 | `pattern-scan/01-session-reader` | None; tested session facts | `main` at `9c83815` |
| 2 | `pattern-scan/02-core-patterns` | Library returns three observations | PR 1 |
| 3 | `pattern-scan/03-frequency-signals` | Library returns six frequency signals | PR 2 |
| 4 | `pattern-scan/04-reports` | Text and JSON renderers | PR 3 |
| 5 | `pattern-scan/05-cli` | Complete opt-in command | PR 4 |

Every PR must pass the full existing test suite plus its focused tests. Keep
each PR to one intentional commit unless a mechanical follow-up is genuinely
separate.

### PR 1 - Codex pattern session reader

PR1 is intentionally a thin reader. Do not build a generalized telemetry
model or preprocess facts for the later frequency signals before the direct
observation rules have produced useful results. Retain only the smallest
privacy-safe event facts needed by `R-READ-01`, `R-RETRY-01`, and `R-TEST-01`.

**Files**

- [x] Add `burnrate/analyser/patterns.py`.
- [x] Add `tests/test_pattern_reader.py`.

**Implementation**

- [x] Discover a file or recursive JSONL directory using existing safe
  filesystem behavior.
- [x] Parse line by line and continue after malformed records.
- [x] Retain only the minimum rule inputs: session identity, deterministic
  event order, source location, normalized read target, normalized command and
  failure fingerprint, test-command classification, and successful mutation
  marker.
- [x] Retain final per-request token usage only where it is needed to preserve
  existing session facts; do not prepare token-threshold data for PR3.
- [x] Deduplicate cumulative token records within each session without
  deduplicating records by timestamp alone.
- [x] Keep the reader's event vocabulary deliberately narrow. Defer bounded
  output sizes, turn-boundary modeling, agent/subagent counts, web counts,
  duration aggregation, and generalized tool taxonomy until the later PR that
  needs them.
- [x] Expose complete, partial, empty, and invalid scan status without changing
  the current CLI.

**Acceptance**

- [x] Repeated cumulative records are counted once.
- [x] Two sessions never share token state.
- [x] Unreadable files preserve readable session results and mark the scan
  partial.
- [x] Message and tool-output bodies are not retained.
- [x] The returned facts are sufficient to implement the three direct
  observation rules without speculative preprocessing for frequency signals.
- [x] Existing tests pass unchanged.

**Excluded:** detectors, catalog metadata, reports, CLI flags, provider
abstraction, generic event types, bounded output sizes, turn-boundary
modeling, agent/subagent counts, web counts, duration aggregation, and
frequency-signal preprocessing.

### PR 2 - Direct observation rules

**Files**

- [x] Extend `burnrate/analyser/patterns.py`.
- [x] Add `burnrate/analyser/pattern_catalog.py` with only implemented rule metadata.
- [x] Add `tests/test_pattern_observations.py`.

**Implementation**

- [x] Implement `R-READ-01`, counting `n - 1` repeats per target and session.
- [x] Implement `R-RETRY-01` as distinct consecutive retry sequences.
- [x] Implement `R-TEST-01`, with successful mutation as a sequence boundary.
- [x] Map real Codex function/custom tool calls and outputs conservatively by call ID, retaining only normalized command/path, failure fingerprints, and mutation status.
- [x] Return the shared result shape with at most three source examples.
- [x] Sort occurrences deterministically.

**Acceptance**

- [x] No pairwise count inflation.
- [x] Success or a changed command/fingerprint ends a retry sequence.
- [x] A successful mutation ends a test-churn sequence.
- [x] Missing required fields suppress the rule.
- [x] One underlying sequence belongs to one rule.

**Excluded:** message similarity, inferred tasks, confidence scores, reviews,
baselines, and frequency thresholds.

### PR 3 - Transparent frequency signals

**Files**

- [ ] Extend `burnrate/analyser/patterns.py`.
- [ ] Extend `burnrate/analyser/pattern_catalog.py`.
- [ ] Add `tests/test_pattern_signals.py`.

**Implementation**

- [ ] Add `R-EXP-01`, `R-SESSION-01`, `R-TOKEN-01`, `R-OUT-01`,
  `R-SUBAGENT-01`, and `R-WEB-01`.
- [ ] Define every threshold as a named constant and catalog field.
- [ ] Count session-level rules as affected sessions.
- [ ] Count web calls and large outputs as direct occurrences.
- [ ] Keep the classification visibly `frequency_signal`.

**Acceptance**

- [ ] Every threshold has immediately-below and at-threshold fixtures.
- [ ] Duration and token calculations are session-local.
- [ ] Missing timestamp, token, output, lineage, or web telemetry suppresses
  only its dependent rule.
- [ ] No signal is described as avoidable or wasteful.

**Excluded:** cache-discontinuity interpretation, personal baselines, threshold
tuning, scores, grades, and estimated savings.

### PR 4 - Concise reports

**Files**

- [ ] Add `burnrate/pattern_report.py`.
- [ ] Add `tests/test_pattern_report.py`.

**Implementation**

- [ ] Rank by occurrence count, then stable rule ID.
- [ ] Render the concise default text contract.
- [ ] Render deterministic JSON from the same result objects.
- [ ] Show thresholds and up to three examples only with `explain=True`.
- [ ] Show one qualified `try_next_experiment` per displayed pattern.
- [ ] State that results are observations or frequency signals, not measured
  waste.

**Acceptance**

- [ ] Text and JSON totals agree exactly.
- [ ] Zero patterns produce a valid, non-alarming report.
- [ ] Unavailable rules are absent.
- [ ] Examples contain source references, not message or output bodies.
- [ ] Snapshot-style tests keep the default output short.

**Excluded:** CLI parsing, color, internationalization, share text, sidecars,
grades, and fixed token estimates.

### PR 5 - Opt-in CLI

**Files**

- [ ] Update `burnrate/main.py`.
- [ ] Update `README.md`.
- [ ] Add CLI and installed-package smoke tests.

**Implementation**

- [ ] Add `--patterns`, `--days`, `--json`, and `--explain`.
- [ ] Restrict the initial feature to the Codex parser with a clear validation
  error for unsupported combinations.
- [ ] Reuse `--log-path` and existing exit-code semantics.
- [ ] Default pattern scans to the last seven days.
- [ ] Document a twenty-day local smoke-test command.

**Acceptance**

- [ ] Running without `--patterns` preserves existing behavior and output.
- [ ] Console-script and `python -m burnrate` entry points agree.
- [ ] Text and JSON work for a file and directory.
- [ ] Invalid, partial, empty, and successful scans return documented codes.
- [ ] Installed-package smoke tests pass.
- [ ] A twenty-day local scan is understandable without `--explain`.

**Excluded:** Claude support, persistence, interactive review, configuration
files, external telemetry, and scoring.

## Cross-PR test contract

Synthetic fixtures must cover:

- repeated and non-repeated reads;
- retries separated by success or a changed command;
- tests separated by successful mutation;
- values below and at every threshold;
- final cumulative usage selection per request;
- unrelated counters in two sessions;
- missing timestamps, output, lineage, and token usage;
- malformed JSON and unreadable files;
- deterministic ranking and text/JSON agreement;
- preservation of the existing non-pattern CLI.

Personal logs are a final smoke test, never the correctness oracle.

## Release completion

The vertical slice is ready when:

- [ ] all five PRs are merged in order;
- [ ] one command produces a concise ranked report from local Codex logs;
- [ ] every displayed number is a direct count or session-local aggregate;
- [ ] every rule exposes its threshold and bounded examples on request;
- [ ] missing telemetry never becomes a finding;
- [ ] existing BurnRate accounting remains unchanged;
- [ ] the full suite and installed-package smoke tests pass;
- [ ] the twenty-day report is useful without reading an evidence schema.

## Simplicity guardrails

- No more than three new production modules.
- No more than nine active rules.
- One result shape and one aggregation path.
- No runtime dependencies, persistence, or network access.
- No natural-language similarity.
- No task episodes, sidecars, baselines, or review gates.
- No score, grade, waste percentage, or fixed waste-token estimate.
- No extension framework before a proven second use case needs one.

If a proposed change does not improve the default ranked report, defer it to
the roadmap.
