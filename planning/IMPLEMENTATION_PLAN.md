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
burnrate patterns --days 20
```

Default output stays short and gives the user one experiment they can understand
and try in under 30 seconds:

```text
BurnRate - 98 Codex sessions over 20 days

Top 3 signals

1. Large outputs often expanded later context
   298 outputs over 16,000 characters in 33 sessions; 30/33 sessions (91%)
   also showed a later input increase over 8,000 tokens (250 temporal pairs).
   Example: 16,220 output characters -> 9,364 additional input tokens
   Try: Cap reads and command output with a range, filter, or line limit.

2. Context grew steadily during sessions
   21 sustained growth runs across 14 sessions. Separately, 16 sessions
   reached at least 80% of the reported context window.

3. Repeated reads were concentrated in a few sessions
   14 repeated reads across 7 sessions.

Check again:
burnrate patterns --days 7

6 more signals: burnrate patterns --days 20 --explain

Coverage: some context and cache-dependent checks were unavailable.
Observations only - this does not measure waste, correctness, or verification.
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
| `R-TOKEN-01` | Sessions over token threshold | Session work tokens exceed 50,000 | frequency signal |
| `R-OUT-01` | Large tool output | One tool result exceeds 16,000 characters | frequency signal |
| `R-SUBAGENT-01` | Subagent-heavy session | At least six subagent spawns occur in one session | frequency signal |
| `R-WEB-01` | Web-heavy session | Count observed web search/fetch calls | frequency signal |

Missing required telemetry suppresses only the affected rule. It does not emit
an unavailable finding.

## Architecture constraints

The accepted v0.2.0 implementation uses four focused production modules. The
fourth module isolates canonical context telemetry so model-stream boundaries,
cache semantics, and ordered carry evidence remain testable without making
`patterns.py` a generalized telemetry framework:

```text
burnrate/
  analyser/
    patterns.py        JSONL reader, session accumulator, detectors
    pattern_catalog.py rule names, thresholds, explanations, experiments
    pattern_context.py canonical context snapshots and context signals
    pattern_report.py  deterministic text and JSON rendering
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

Implement the feature in six sequential PRs. Create each branch from the
updated `main` after the preceding PR has merged.

| PR | Branch | User-visible outcome | Depends on |
| --- | --- | --- | --- |
| 1 | `pattern-scan/01-session-reader` | None; tested session facts | `main` at `9c83815` |
| 2 | `pattern-scan/02-core-patterns` | Library returns three observations | PR 1 |
| 3 | `pattern-scan/03-frequency-signals` | Library returns ten frequency signals | PR 2 |
| 4 | `pattern-scan/04-reports` | Text and JSON renderers | PR 3 |
| 5 | `pattern-scan/05-cli` | Complete opt-in command | PR 4 |
| 6 | `pattern-scan/06-coaching-report` | Adoption-focused experiment and rerun loop | PR 5 |

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

### PR 2 - Direct observation rules (follow-up investigation open)

**Files**

- [x] Extend `burnrate/analyser/patterns.py`.
- [x] Add `burnrate/analyser/pattern_catalog.py` with only implemented rule metadata.
- [x] Add `tests/test_pattern_observations.py`.

**Implementation**

- [x] Implement `R-READ-01`, surfacing a target after its third read in a
  session so a second read remains ordinary verification.
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

**Real-log extension and interpretation guardrail**

- [x] Map `response_item.function_call` and `custom_tool_call` records using
  their JSON arguments or inputs.
- [x] Pair function/custom tool outputs by `call_id` and retain only exit
  status, a bounded failure fingerprint, and successful mutation status.
- [x] Recognize `patch_apply_end` as a successful mutation boundary when its
  structured success field is true.
- [x] Extract literal read targets from conservative command forms such as
  `Get-Content`, `cat`, `type`, `head`, `tail`, and `sed`; reject variable
  placeholders such as `$file.FullName`.
- [x] Do not retain message bodies, reasoning bodies, or tool-output bodies.
- [x] Keep repeated reads classified as observations. A repeated read is not
  described as unnecessary, avoidable, wasteful, or inefficient without
  additional evidence.

**PR2 local smoke-test record (2026-08-03)**

The 20-day scan covered 15 July through 3 August 2026. The reproducible
rerun selected files containing at least one event timestamp in that UTC window:
42 local Codex JSONL files and 72 sessions:

- `R-READ-01`: 87 occurrences across 11 sessions.
- `R-RETRY-01`: 0 qualifying consecutive retry occurrences.
- `R-TEST-01`: 0 qualifying test-churn occurrences.

PR2 follow-up rerun (2026-08-04) found 1 test candidate (a repository-specific
unittest invocation), 0 qualifying test-churn occurrences, 0 qualifying retry
occurrences, and 5 repeated-command candidates suppressed because failure
evidence was unavailable. The scan had 1 malformed record and remained
complete; these diagnostics are reported separately from zero occurrences.
The prior 52-file figure is not reproducible from the current inventory and is
not used for this rerun.

These are direct observations from the local logs, not proof of unnecessary
work or measured waste. The smoke test is evidence that the reader and rules
can operate on real Codex envelopes; synthetic fixtures remain the correctness
oracle.
**Follow-up investigation — PR2 remains open**

- [x] Audit real `function_call`/`function_call_output` pairing for failed shell
  commands, including delayed or interleaved outputs and output formats that
  report failure without the currently recognized exit-status wording.
- [x] Add fixtures for every observed failure-status envelope and prove the
  failure fingerprint is attached to the correct call without retaining output
  bodies.
- [x] Add a diagnostic count for repeated command candidates suppressed because
  one or more attempts lack required failure evidence.
- [x] Deep-dive `R-TEST-01` against real Codex test invocations, including
  `pytest`, `unittest`, repository-specific test wrappers, and commands whose
  test intent is available only in structured tool arguments.
- [x] Verify test-command normalization across equivalent invocations and ensure
  changed commands start new sequences.
- [x] Verify successful mutation boundaries from `patch_apply_end` and successful
  shell commands, including mutations between test attempts and interleaved
  read/tool events.
- [x] Run a focused 20-day real-log review for test candidates and suppressed
  retry candidates before closing PR2.

**Follow-up acceptance**

- [x] A repeated failed command is reported when both attempts have reliable
  failure evidence, regardless of the recognized output envelope wording.
- [x] Missing failure evidence remains unavailable and is distinguishable from
  zero retry occurrences.
- [x] `R-TEST-01` identifies actual repeated test commands without treating
  generic shell commands as tests.
- [x] A successful observed mutation always ends test churn, while unrelated
  reads and tool events do not accidentally end it.
- [x] The smoke-test record is updated with confirmed findings and suppressed
  candidates separately.
  
### PR 3 - Transparent frequency signals

**Files**

- [x] Extend `burnrate/analyser/patterns.py`.
- [x] Extend `burnrate/analyser/pattern_catalog.py`.
- [x] Add `tests/test_pattern_signals.py`.

**Implementation**

- [x] Add `R-EXP-01`, `R-SESSION-01`, `R-TOKEN-01`, `R-OUT-01`,
  `R-SUBAGENT-01`, and `R-WEB-01`.
- [x] Define every threshold as a named constant and catalog field.
- [x] Count session-level rules as affected sessions.
- [x] Count web calls and large outputs as direct occurrences.
- [x] Keep the classification visibly `frequency_signal`.

**Acceptance**

- [x] Every threshold has immediately-below and at-threshold fixtures.
- [x] Duration and token calculations are session-local.
- [x] Missing timestamp, token, output, lineage, or web telemetry suppresses
  only its dependent rule.
- [x] No signal is described as avoidable or wasteful.

**Excluded:** cache-discontinuity interpretation, personal baselines, threshold
tuning, scores, grades, and estimated savings.

### PR 3.5 - Real-log signal correctness

**Purpose**

Correct the parser assumptions exposed by the PR3 three-week Codex-log review
before reports make those signals user-facing.

**Files**

- [x] Extend `burnrate/analyser/patterns.py`.
- [x] Extend `tests/test_pattern_reader.py`.
- [x] Extend `tests/test_pattern_observations.py`.
- [x] Extend `tests/test_pattern_signals.py`.

**Implementation**

- [x] Recognize native `web_search_call` and `web_search_end` telemetry and
  count each logical web call once, rather than counting both lifecycle events.
- [x] Reject command switches such as `-Raw` as read targets; retain only
  verified literal paths.
- [x] Preserve one monotonic event sequence and pending call/output matching
  across every file belonging to the same session.
- [x] Define the native `token_count` accounting source explicitly: use a
  stable cumulative session total when available, otherwise document and
  correctly deduplicate per-request snapshots without a request ID.
- [x] Add diagnostics for frequency rules suppressed by unavailable native
  telemetry, including turn, lineage, and web coverage.

**Acceptance**

- [x] Fixtures cover `web_search_call`/`web_search_end` and emit one
  `R-WEB-01` occurrence per logical call.
- [x] Variable paths and option-only read commands never create a synthetic
  target such as `-Raw`.
- [x] A session spanning multiple JSONL files keeps event order and pairs a
  call in one file with its output in another.
- [x] Native token-count fixtures prove the selected accounting total is not
  inflated by repeated snapshots.
- [x] A repeat three-week scan reports non-zero parsed web telemetry and no
  synthetic `-Raw` read target.

**Excluded:** changing the published thresholds, inferring missing telemetry,
personal baselines, scores, grades, and estimated savings.

### PR 3.6 - Transparent context-pressure signals

**Purpose**

Measure context pressure and token intensity from provider-reported counters
without inspecting message bodies or claiming that observed usage is
inefficient.

**Files**

- [x] Keep `burnrate/analyser/patterns.py` focused on record reading,
  session orchestration, and compatibility with existing observations.
- [x] Add `burnrate/analyser/pattern_context.py` for canonical snapshots and
  context-pressure signal detection.
- [x] Make `burnrate/analyser/pattern_catalog.py` the source of truth for
  thresholds and metadata rather than a re-export-only module.
- [x] Extend `tests/test_pattern_reader.py`.
- [x] Add `tests/test_pattern_context.py`.

**Implementation**

### 3.6a - Canonical context telemetry

- [x] Define one numeric `ContextSnapshot` containing only source reference,
  sequence, timestamp, session ID, model ID, context-window tokens, input
  tokens, cached-input tokens, cache-write-input tokens, output tokens,
  reasoning-output tokens, and total tokens.
- [x] Normalize the provider field mapping explicitly, including whether
  `input_tokens` includes cached input. Reject incompatible or ambiguous
  combinations instead of guessing.
- [x] Retain ordered snapshots per session and model. A model change starts a
  new context stream; counters are never combined across models or sessions.
- [x] Preserve a separate numeric output event sequence so carry detection can
  prove that output preceded later token evidence without retaining output
  bodies.
- [x] Bound retained snapshot memory and retain no message, reasoning, query,
  result, or tool-output body.

### 3.6b - Context-pressure signals

- [x] Add named constants and catalog fields for the utilization threshold,
  sustained-growth run length, growth qualification, cache-volume threshold,
  and carry input increase.
- [x] Add `R-CTX-01` for peak observed input/context-window utilization,
  calculated only from a compatible snapshot and reported context window.
- [x] Add `R-CTX-02` for sustained observed input-token growth across the named
  number of consecutive snapshots; reset on session/model boundaries, missing
  snapshots, counter decreases, and counter resets.
- [x] Add `R-CACHE-01` only when input and cached-input counters share a known
  semantic basis; calculate non-negative uncached input without double-counting
  total input.
- [x] Add `R-CARRY-01` only when an ordered large-output event is followed by a
  qualifying input increase in the same session/model stream. Describe this as
  a temporal relationship, never a causal attribution.

### 3.6c - Transparent result contract

- [x] Expose measured value, unit, threshold, counting scope, source/model
  scope, and telemetry availability for every new signal.
- [x] Use neutral catalog and result language: context pressure, growth, cache
  reuse, token intensity, observed, and temporal relationship.
- [x] Keep existing PR 3 and PR 3.5 signal behavior unchanged.

**Review follow-up (2026-08-08)**

- [x] Split context streams at every observed model transition. An `A -> B ->
  A` sequence creates three streams and never combines the two `A` epochs for
  growth or carry detection. Carry explicit `turn_context` model metadata into
  later token snapshots when the snapshot does not repeat the model ID.
- [x] Treat missing cache-counter semantics as unavailable. Do not default an
  absent `input_includes_cached` field to true, and reject combinations where
  cached input exceeds gross input instead of clamping the derived value.
- [x] Calculate cumulative token totals without double-counting cached input
  within input tokens or reasoning output within output tokens. If an explicit
  compatible total is unavailable, suppress the dependent rule rather than
  summing semantically overlapping counters.
- [x] Remove the duplicate thresholds and catalog metadata from
  `patterns.py`. Detection and result metadata must read the same values from
  `pattern_catalog.py` so the catalog is the sole runtime source of truth.
- [x] Include the model ID and a stable stream/epoch scope in each context
  signal example and aggregate result so the reported source/model scope is
  directly inspectable.

**Review follow-up acceptance**

- [x] An `A -> B -> A` fixture cannot qualify a growth run or carry pair by
  joining observations from the two `A` epochs.
- [x] A native `turn_context` model change starts a new stream even when later
  `token_count` records omit their model ID.
- [x] Missing or contradictory cache semantics suppress `R-CACHE-01` and are
  reported as unavailable telemetry.
- [x] Cumulative usage fixtures containing gross input, cached input, output,
  and reasoning output prove that overlapping counters are counted once.
- [x] Changing a threshold in `pattern_catalog.py` changes both detection and
  reported metadata without a second edit.
- [x] Every emitted context signal identifies its model and stream epoch in
  the transparent result contract.

**Acceptance**

- [x] Every threshold, run length, and qualifying increase has immediately-
  below and at-threshold fixtures.
- [x] Snapshot fixtures prove ordered, session-local, model-local retention and
  no cross-model or cross-session aggregation.
- [x] Context utilization uses the provider-reported context window and is
  unavailable when that window or compatible input telemetry is missing.
- [x] Growth runs reset at session/model boundaries, counter resets, and
  missing snapshots.
- [x] Cached and uncached input calculations never produce negative values or
  double-count total input; incompatible counter semantics suppress the rule.
- [x] `R-CARRY-01` requires ordered output and subsequent token evidence and is
  absent when either side is unavailable or bodies are the only evidence.
- [x] No rule retains message, reasoning, query, result, or tool-output bodies;
  retained snapshots contain numeric counters and source references only.
- [x] Every new result exposes its measured value, unit, threshold, scope, and
  telemetry availability.
- [x] Catalog, examples, and result text use neutral terms such as context
  pressure, growth, cache reuse, and token intensity; they never claim
  inefficiency, bloat, waste, or savings.

**Excluded:** task-quality judgments, causal attribution, personal baselines,
provider comparisons, scores, grades, waste percentages, threshold tuning,
and estimated savings.

### PR 4 - Concise reports

**Files**

- [x] Add `burnrate/analyser/pattern_report.py`.
- [x] Add `tests/test_pattern_report.py`.

**Implementation**

- [x] Add a deterministic, non-severity `display_priority` tier to the catalog:
  direct intervention (`R-RETRY-01`, `R-TEST-01`), context pressure
  (`R-CTX-01`, `R-CTX-02`, `R-CARRY-01`, `R-OUT-01`), repeated exploration
  (`R-READ-01`, `R-EXP-01`), then resource and orchestration volume
  (`R-TOKEN-01`, `R-CACHE-01`, `R-SESSION-01`, `R-SUBAGENT-01`,
  `R-WEB-01`). Within one tier, rank by affected sessions, occurrence count,
  then stable rule ID. The tier controls display order only and is never
  described as severity, risk, waste, or a score.
- [x] Render the concise default text contract.
- [x] Show at most three findings in default text and state how many additional
  signals are available with `--explain`.
- [x] Put the rule's counting scope and affected-session count on each default
  finding line so unlike units such as calls, sequences, streams, and sessions
  are never presented as directly comparable totals.
- [x] Render deterministic JSON from the same result objects. JSON is not
  display-capped and uses a versioned envelope containing `schema_version`,
  scan status, session count, telemetry coverage, and the complete pattern
  list.
- [x] Show thresholds, measured values, source/model scope, telemetry
  requirements, and up to three source examples only with `explain=True`.
- [x] Show one qualified `try_next_experiment` for the highest-priority
  actionable finding in default text. With `explain=True`, show one qualified
  experiment per displayed pattern.
- [x] Add a compact default coverage line whenever required telemetry was
  unavailable. Suppressed rules remain absent, but missing telemetry must not
  be presented as a measured zero.
- [x] State that results are observations or frequency signals, not measured
  waste. Also state that the scan does not measure code correctness or
  successful verification.
- [x] Label any aggregate occurrence total as rule matches rather than unique
  actions, because one observed event can contribute to more than one rule.

**Acceptance**

- [x] Text and JSON totals agree exactly.
- [x] Default text contains no more than three findings and names the number of
  additional signals when the complete JSON result contains more.
- [x] Direct intervention findings sort ahead of context pressure, repeated
  exploration, and resource/orchestration volume regardless of raw count;
  ties within a tier follow affected sessions, count, then rule ID.
- [x] Every default finding exposes both its native count scope and affected
  sessions without implying that unlike scopes are comparable.
- [x] Default text shows exactly one primary experiment; explain output shows
  one experiment for each displayed pattern.
- [x] Zero patterns produce a valid, non-alarming report.
- [x] Unavailable rules are absent.
- [x] Missing telemetry produces a compact coverage caveat and never becomes a
  finding or a zero count.
- [x] Examples contain source references, not message or output bodies.
- [x] JSON includes every result and stable scan metadata even when default
  text displays only the first three findings.
- [x] The trust boundary explicitly says that the scan does not measure code
  correctness, successful verification, or wasted work.
- [x] Snapshot-style tests keep the default output short.

**Excluded:** CLI parsing, color, internationalization, share text, sidecars,
grades, and fixed token estimates.

### PR 5 - Opt-in CLI

**Files**

- [x] Update `burnrate/main.py`.
- [x] Update `README.md`.
- [x] Add CLI and installed-package smoke tests.

**Implementation**

- [x] Add `--patterns`, `--days`, `--json`, and `--explain`.
- [x] Restrict the initial feature to the Codex parser with a clear validation
  error for unsupported combinations.
- [x] Reuse `--log-path` and existing exit-code semantics.
- [x] Default pattern scans to the last seven days.
- [x] Document a twenty-day local smoke-test command.

**Acceptance**

- [x] Running without `--patterns` preserves existing behavior and output.
- [x] Console-script and `python -m burnrate` entry points agree.
- [x] Text and JSON work for a file and directory.
- [x] Invalid, partial, empty, and successful scans return documented codes.
- [x] Installed-package smoke tests pass.
- [x] A twenty-day local scan is understandable without `--explain`.

**Excluded:** Claude support, persistence, interactive review, configuration
files, external telemetry, and scoring.

### PR 6 - Adoption-focused coaching report

PR6 changes the default presentation from a scan ledger into a small coaching
loop. Its product promise is: "In 30 seconds, find one workflow change worth
trying this week." It does not change detector thresholds, classifications, or
the complete evidence contract.

**Files**

- [x] Update `burnrate/analyser/pattern_report.py`.
- [x] Update `burnrate/analyser/pattern_catalog.py` only where experiment text
  or deterministic experiment eligibility metadata is required.
- [x] Update `burnrate/main.py` and `README.md`.
- [x] Extend `tests/test_pattern_report.py` and `tests/test_cli.py`.

**Implementation**

- [x] Add `burnrate patterns` as the preferred command while retaining the PR5
  `--patterns` form as a compatibility alias. Both forms must use the same scan,
  detection, rendering, and exit-code paths.
- [x] Lead the default text with three grouped, interpretable insights. Each
  insight contains one concise qualified experiment, and the report provides
  one deterministic `Check again` command for the set.
- [x] Keep raw detector rules in explain output and JSON while grouping related
  rules in default text (large output plus temporal carry, input growth plus
  context pressure, and repeated reads).
- [x] Select the primary experiment independently from the catalog's complete
  signal display order. A pattern is broadly supported when it affects more
  than one session or has more than one native occurrence. Select among broadly
  supported patterns by affected sessions descending, display priority,
  occurrence count descending, then stable rule ID. If none qualify, fall back
  to the existing display order. This is a presentation rule, not severity,
  risk, waste, or a score.
- [x] Show affected-session prevalence as `affected/observed sessions` and a
  whole-number percentage on the primary finding. Keep the rule's native count
  and native scope as supporting evidence so unlike occurrence units are not
  compared.
- [x] Show at most two `Other top signals`, preserving the catalog display order
  after removing the primary pattern. The default therefore displays at most
  three distinct patterns in total.
- [x] Label the displayed set as the top three signals and include each
  signal's catalog-driven threshold or measurement description in the default
  text when one exists.
- [x] Include one compact example per displayed signal with a shortened source
  reference and at most one normalized target, command, or measured value;
  never print message or tool-output bodies.
- [x] Remove aggregate rule matches from the default text. Retain the exact
  total in explain output and the complete JSON envelope, labelled "rule
  matches", because underlying events can match more than one rule.
- [x] Render the exact command needed to inspect more signals and a compact
  seven-day rerun command. The CLI owns command construction; the report
  renderer receives the final command hints and does not reconstruct parser or
  path arguments from prose.
- [x] Replace the default telemetry diagnostic list with one plain-language
  coverage sentence. Keep per-telemetry counts and suppressed-rule detail in
  explain output and JSON.
- [x] End with one compact trust-boundary sentence stating that the observations
  do not measure waste, code correctness, or successful verification.
- [x] Keep explain output evidence-first: complete ranked signals, thresholds,
  native counts, affected sessions, telemetry requirements, bounded source
  references, and one qualified experiment per pattern.
- [x] Add terminal-aware presentation styling: compact briefing header, ASCII
  insight cards, restrained semantic color, and a quiet footer. Styling is
  enabled only for interactive text terminals; redirected text and JSON remain
  stable and color-free.
- [x] Calibrate productivity defaults: 16,000-character tool outputs,
  8,000-token output-to-input carry, three growth snapshots with a minimum of
  `max(4,000, 2% of context window)` tokens per step, 80% context review and
  90% fresh-context thresholds, and three same-target reads per session.
- [x] Add the selected primary pattern ID and deterministic selection basis to a
  `presentation` object in JSON and increment `schema_version`. JSON remains
  uncapped and contains every detected result.
- [x] Document when to run the command: after a working week, before a workflow
  retrospective, or after trying a process change. Do not claim improvement
  without a separately observed follow-up scan.

**Acceptance**

- [x] A fixture with large-output and carry rules groups them into one
  output-to-context insight rather than displaying two disconnected findings.
- [x] Default text contains three grouped insights, one experiment per insight,
  one rerun command, and no more than three displayed insight blocks.
- [x] The primary prevalence numerator equals `affected_sessions`, its
  denominator equals scanned sessions, and percentage rounding is deterministic.
- [x] Native units such as growth runs, occurrences, streams, and pairs remain
  labelled and are never presented as directly comparable totals.
- [x] Catalog thresholds and units are visible in the top-three evidence lines;
  changing a catalog parameter changes both detection and displayed metadata.
- [x] Aggregate rule matches are absent from default text and agree exactly
  between explain output and JSON.
- [x] Broad token-volume thresholds and isolated retry observations do not
  displace the grouped output/context, growth/pressure, or repeated-read
  insights when those groups are available.
- [x] The additional-signal count excludes the primary and displayed secondary
  patterns and the shown explain command reproduces the same scan window.
- [x] Missing telemetry produces one non-alarming default coverage sentence;
  unavailable rules remain absent rather than becoming findings or zeroes.
- [x] `burnrate patterns` and `burnrate --patterns` produce equivalent report
  objects and documented exit codes for successful, partial, empty, and invalid
  scans.
- [x] JSON increments its schema version, identifies the primary pattern and
  selection basis, and still includes every result and telemetry detail.
- [x] Zero patterns produce a calm report with no fabricated experiment.
- [x] Snapshot tests keep the default report readable at a glance and preserve
  the one-line trust boundary.

**Excluded:** persistence, automatic before/after comparisons, scores, grades,
severity labels, inferred savings, notifications, interactive prompts, and
external telemetry.

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

### Verification record

On 2026-08-16, from the `codexpattern` branch, the checks below were run with
Python's temporary directory redirected to the workspace-local `.test-tmp`
directory so fixture and build files could be created without relying on the
system temporary directory:

- `\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` — **pass**;
  116 tests ran and all passed.
- `\.venv\\Scripts\\python.exe scripts\\smoke_build.py` — **pass**;
  the sdist and wheel built, the wheel installed into a disposable virtual
  environment, both console-script and `python -m burnrate` help commands
  passed, and both invalid-path exit checks passed.

On 2026-08-16, the bundled pricing tables were refreshed against the current
[OpenAI API pricing](https://developers.openai.com/api/docs/pricing) and
[Anthropic Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing).
The refresh corrected the standard GPT-5.6 Terra/Luna rates, added current
Codex/Daybreak IDs, added current Claude model IDs and legacy-compatible
aliases, and retained the documented 5-minute cache-write limitation. The
full 116-test suite, including exact pricing fixtures and metadata checks,
passed after the refresh.

The raw `codex-auto-review` label was also investigated. Its records expose no
underlying model or billable dollar SKU. BurnRate now applies the published
GPT-5.4 standard API rate as a qualified API-equivalent estimate, based on the
observed Codex routing, and documents that this is not an invoice rate.

These results verify the automated suite and packaging path only. Release
integration into `main` is the remaining repository operation.

On 2026-08-16, the documented local smoke test was also run:

- `\\.venv\\Scripts\\python.exe -m burnrate patterns --parser codex --days 20
  --log-path "$HOME/.codex/sessions"` — **pass**; 133 sessions across 105
  files produced 9 raw signals.
- The default report is **genuinely actionable for an initial experiment**:
  it presents three bounded insights, gives prevalence and native counts,
  includes one concrete workflow change per insight, and supplies a directly
  runnable seven-day `Check again` command. The leading recommendation to cap
  large reads/output is especially clear, while the fresh-context and repeated-
  read recommendations are also immediately testable.
- The report remains appropriately qualified: it describes temporal evidence
  rather than causation, calls out incomplete or unavailable telemetry, and
  states that it does not measure waste, correctness, or verification. This is
  sufficient to mark the default-report usefulness gate complete, but not to
  claim that any intervention improved outcomes.

## Release completion

The vertical slice is ready when:

- [x] all six planned implementation stages are integrated into `main` in order;
- [x] one command produces a concise ranked report from local Codex logs;
- [x] every displayed number is a direct count or session-local aggregate;
- [x] every rule exposes its threshold and bounded examples on request;
- [x] missing telemetry never becomes a finding;
- [x] existing BurnRate accounting remains unchanged;
- [x] the full suite and installed-package smoke tests pass;
- [x] the twenty-day report is useful without reading an evidence schema.

The behavioral, evidence, and integration gates are complete. The repository is
ready for the 0.2.0 release verification below.

After the merge into `main` on 2026-08-16, the final verification was repeated:

- `\.venv\\Scripts\\python.exe -m unittest discover -s tests -q` — **pass**;
  116 tests ran and all passed.
- `\.venv\\Scripts\\python.exe scripts\\smoke_build.py` — **pass**;
  the 0.2.0 sdist and wheel built, installed, and passed console-script,
  module-help, and invalid-path checks in a disposable environment.

## Simplicity guardrails

- **Accepted v0.2.0 exception:** four focused analyser modules and 13 active
  rules (three observations plus ten frequency signals). The additional
  `pattern_context.py` module and four context/cache/carry signals were added
  because the 20-day local scan showed actionable context pressure and the
  module boundary keeps provider telemetry semantics explicit and testable.
  This is a fixed release baseline, not permission to grow a detector
  framework; further rules or modules require a new evidence-backed roadmap
  decision.
- One result shape and one aggregation path.
- No runtime dependencies, persistence, or network access.
- No natural-language similarity.
- No task episodes, sidecars, baselines, or review gates.
- No score, grade, waste percentage, or fixed waste-token estimate.
- No extension framework before a proven second use case needs one.

If a proposed change does not improve the default ranked report, defer it to
the roadmap.
