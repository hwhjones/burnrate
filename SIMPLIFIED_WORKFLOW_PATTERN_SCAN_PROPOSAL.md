# Simplified Workflow Pattern Scan Proposal

## Starting point

Create a new branch from `main` at `9c83815` (`docs: prioritize deterministic
waste-signature pilot`), which is the current local `main` tip. Do not branch
from, merge, or cherry-pick the structured-trace pilot as a whole.

The new work should preserve BurnRate's existing usage and cost reporting. It
adds one small, opt-in Codex workflow pattern scan whose job is:

> Read local logs, count a few transparent patterns, rank them, and show one
> qualified experiment for each pattern.

The product goal is TokenHabit-equivalent usefulness, not equivalent scoring or
architecture.

## Product contract

The first useful command is:

```console
burnrate --patterns --parser codex --days 20
```

Default output is deliberately short:

```text
BurnRate workflow pattern scan - last 20 days
Sessions: 42  |  pattern occurrences: 38

Repeated exploration                 x27
Repeated file reads                  x10
Ineffective retries                   x1

Try next experiment:
Narrow the exploration scope before starting another sweep.

Use --explain for examples and thresholds. These are deterministic signals,
not measured waste or proof that the work was avoidable.
```

The scan reports occurrences and recurring workflow patterns, not habits. A
future reviewed workflow may promote a pattern recurring across independent
sessions or days to a habit candidate, but that lifecycle is outside this
release.

The scan must never report a waste percentage, letter grade, fixed wasted-token
estimate, or composite score.

## Scope

### Initial patterns

Implement only patterns that can be explained with direct local evidence.

| ID | Pattern | Detection | Classification |
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

If a field required by a rule is absent, skip that rule for the affected
session. Do not emit an unavailable catalog record in the default report.

Thresholds are named module constants and shown by `--explain`. They are
starting heuristics, not calibrated truths.

### Explicit non-goals

Do not port or rebuild these features:

- message similarity, containment, character n-grams, BM25, or TF-IDF;
- semantic subagent comparison;
- inferred task episodes or correctable episode boundaries;
- candidate review sidecars or review-coverage gates;
- user or repository baselines;
- confidence ladders or independent-signal scoring;
- missing-evidence catalog entries in normal output;
- cross-session token-exposure attribution;
- recommendations conditioned on a review workflow;
- waste-token estimates, grades, or composite scores.

Raw message bodies are not required for the initial scanner and must not be
retained or printed.

## Minimal architecture

Add three modules and make one small CLI change:

```text
burnrate/
  patterns.py          JSONL scan, session accumulator, and detectors
  pattern_catalog.py   names, explanations, classifications, experiments
  pattern_report.py    text and JSON rendering
  main.py              --patterns, --days, --json, and --explain routing
```

Do not create a generic event framework. `patterns.py` may read Codex JSONL
records directly and retain only the fields needed by the nine rules.

### Internal data contract

Use one result shape throughout scanning, aggregation, JSON, and text output:

```python
{
    "id": "R-READ-01",
    "name": "Repeated file reads",
    "classification": "observation",
    "count": 10,
    "affected_sessions": 6,
    "explanation": "The same normalized file was read more than once in a session.",
    "try_next_experiment": "Reference the earlier read when it is still current.",
    "examples": [
        {"filepath": "...jsonl", "line": 123, "target": "src/app.py"}
    ],
}
```

Keep at most three source-linked examples per pattern. Text output hides examples
unless `--explain` is supplied. JSON uses the same counts and includes examples.

### Session accumulator

For each JSONL file/session, retain only:

- first and last valid timestamps;
- final per-request token usage needed to avoid cumulative double counting;
- normalized read targets and command names;
- tool result status, error fingerprint, and output character count;
- successful mutation markers;
- turn boundaries;
- subagent spawn and web call counts;
- source filepath and line number.

Aggregate within a session first. Aggregate pattern occurrences across sessions
only after each session has produced its own counts. Never subtract cumulative
token counters belonging to different sessions.

## Detection rules

Each pattern has one function returning zero or more occurrences. Supporting
events enrich an occurrence; they do not create parallel findings.

Normalization should be intentionally small:

- lowercase tool names and command executables;
- collapse whitespace;
- normalize path separators;
- resolve obvious quoted file arguments for read tools;
- remove volatile timestamps and UUID-like values from failure fingerprints.

Do not normalize natural-language messages.

Repeated reads count `n - 1` for each repeated target per session. Retry and
test rules count distinct retry sequences rather than every pairwise
combination. Frequency rules normally count affected sessions, except web calls
and large outputs, which retain their direct occurrence count.

## CLI behavior

`--patterns` is opt-in and Codex-only for the first release. Existing BurnRate
commands and output remain unchanged.

```console
burnrate --patterns                         # Codex, last 7 days
burnrate --patterns --days 20
burnrate --patterns --log-path C:\logs
burnrate --patterns --json
burnrate --patterns --explain
```

Exit codes follow the existing parser contract:

- `0`: completed scan, including zero detected patterns;
- `1`: partial scan because some files could not be read;
- `2`: invalid top-level input path.

## Pull request structure

Build the feature as five sequential PRs. Create each branch from the updated
`main` after its dependency has merged. Do not keep a long-lived stack with all
five PRs open against one another.

| PR | Branch | Outcome | Depends on |
| --- | --- | --- | --- |
| 1 | `pattern-scan/01-session-reader` | Minimal Codex session facts | `main` at `9c83815` |
| 2 | `pattern-scan/02-core-patterns` | Three direct observation rules | PR 1 |
| 3 | `pattern-scan/03-frequency-signals` | Six transparent threshold signals | PR 2 |
| 4 | `pattern-scan/04-reports` | Stable text and JSON reports | PR 3 |
| 5 | `pattern-scan/05-cli` | Usable opt-in command and documentation | PR 4 |

Each PR should contain one intentional commit unless a mechanical documentation
or test correction genuinely needs to be separate. Every PR must pass the full
existing suite plus its focused tests before merge.

### PR 1 - Add the Codex pattern session reader

**Objective:** Convert each local Codex JSONL file into a small session summary
without changing the existing usage parser or CLI.

**Files:**

- add `burnrate/patterns.py`;
- add `tests/test_pattern_reader.py`.

**Includes:**

- reuse the existing safe file-discovery and diagnostics behavior where practical;
- bounded, line-by-line JSONL parsing;
- the session accumulator fields listed above;
- final per-request token selection within each session;
- source filepath and line references;
- explicit partial-scan and invalid-path results.

**Acceptance checks:**

- malformed records do not stop later records from being read;
- unreadable files make the scan partial while preserving readable sessions;
- repeated cumulative token records are counted once;
- two sessions never share cumulative token state;
- no message body is retained;
- the existing BurnRate CLI and parser tests remain unchanged and pass.

**Out of scope:** detectors, catalog text, reports, CLI flags, generalized event
types, and provider abstraction.

### PR 2 - Add the three direct observation rules

**Objective:** Produce useful findings from evidence that does not require a
subjective threshold.

**Files:**

- extend `burnrate/patterns.py`;
- add `burnrate/pattern_catalog.py` with metadata for only the implemented rules;
- add `tests/test_pattern_observations.py`.

**Rules:**

- `R-READ-01` repeated file read;
- `R-RETRY-01` ineffective retry;
- `R-TEST-01` test churn.

**Acceptance checks:**

- repeated reads count `n - 1`, not pairwise combinations;
- retries are separated by success or a changed command/fingerprint;
- a successful mutation separates test sequences;
- every occurrence has one rule owner and up to three source examples;
- aggregation is session-first and deterministic;
- no rule emits when its required field is absent.

**Out of scope:** message similarity, inferred task boundaries, confidence
scoring, reviews, recommendations in terminal output, and frequency thresholds.

### PR 3 - Add transparent frequency signals

**Objective:** Add TokenHabit-style breadth using plainly disclosed counts,
without converting frequency into a waste claim.

**Files:**

- extend `burnrate/patterns.py`;
- extend `burnrate/pattern_catalog.py`;
- add `tests/test_pattern_signals.py`.

**Rules:**

- `R-EXP-01` exploration pile-up;
- `R-SESSION-01` long session;
- `R-TOKEN-01` token pile-up;
- `R-OUT-01` large tool output;
- `R-SUBAGENT-01` subagent-heavy session;
- `R-WEB-01` web-heavy session.

**Acceptance checks:**

- every threshold is a named constant and appears in rule metadata;
- immediately-below and at-threshold fixtures exist for every rule;
- session duration uses valid timestamps from one session only;
- token totals are calculated per session before aggregation;
- missing output, lineage, token, or timestamp telemetry suppresses only the affected rule;
- signals remain visibly classified as `frequency_signal`.

**Out of scope:** baseline comparisons, threshold tuning, cache-discontinuity
interpretation, scoring, and claims that a signal was avoidable.

### PR 4 - Add concise workflow pattern reports

**Objective:** Turn scanner results into the useful product: a ranked list with
one qualified experiment per pattern.

**Files:**

- add `burnrate/pattern_report.py`;
- add `tests/test_pattern_report.py`.

**Includes:**

- deterministic ranking by count, then stable rule ID;
- the concise default text contract shown above;
- stable JSON using the same result objects and totals;
- optional thresholds and up to three examples when `explain=True`;
- one `try_next_experiment` from catalog metadata;
- an explicit footer stating that findings are observations or frequency signals, not measured waste.

**Acceptance checks:**

- text and JSON totals agree exactly;
- zero findings produce a valid, non-alarming report;
- examples never contain message or tool-output bodies;
- unavailable rules are absent rather than printed;
- snapshot-style fixtures keep the default report short.

**Out of scope:** CLI argument parsing, color, internationalization, grades,
share text, fixed token estimates, and sidecar review output.

### PR 5 - Expose the opt-in workflow pattern CLI

**Objective:** Make the vertical slice usable from an installed BurnRate
package without changing the existing default command.

**Files:**

- update `burnrate/main.py`;
- update `README.md`;
- add or extend CLI and installed-package smoke tests.

**Includes:**

- `--patterns`, `--days`, `--json`, and `--explain`;
- Codex-only validation for the first release;
- existing `--log-path` support;
- existing exit-code behavior;
- last-seven-days default selection;
- a documented twenty-day local smoke-test command.

**Acceptance checks:**

- running without `--patterns` produces the existing output and behavior;
- console-script and `python -m burnrate` entry points agree;
- text and JSON modes work against a file and a directory;
- invalid, partial, empty, and successful scans return the documented codes;
- the installed-package smoke test passes;
- a twenty-day local scan yields a concise ranked report that is understandable without `--explain`.

**Out of scope:** Claude support, interactive review, persistence, configuration
files, telemetry upload, and any scoring model.

### Merge and release discipline

- Merge PRs in numerical order; rebase each new branch on the merged `main`.
- Do not add later-PR scaffolding to an earlier PR.
- Do not copy the experimental `burnrate/traces/` package into the new branch.
- If a rule needs message similarity, a baseline, or a review workflow, remove
  it from this release instead of expanding the architecture.
- After PR 5, release the complete vertical slice as one version. Do not publish
  partially wired scanner or reporting modules as separate user-facing releases.

The five PRs are delivery slices, not new product milestones. Together they
form one deliberately small workflow-pattern-scan milestone.

## Testing

Use synthetic session fixtures covering:

- repeated and non-repeated reads;
- retries separated by success or a changed command;
- tests separated by a successful mutation;
- values immediately below and at each frequency threshold;
- cumulative token records deduplicated per request;
- two sessions with unrelated cumulative token counters;
- missing timestamps, output content, lineage, and token usage;
- malformed JSON and an unreadable file;
- deterministic ranking and text/JSON count agreement;
- preservation of the existing non-pattern CLI output.

Do not use twenty days of personal logs as the correctness test. Use them only
as a final smoke test after deterministic fixtures pass.

## Completion criteria

The simplified feature is complete when:

- one command produces a concise, frequency-ranked workflow pattern report from local
  Codex logs;
- every displayed number is a direct count or a per-session aggregate;
- every rule exposes its threshold and up to three source examples on request;
- missing telemetry suppresses only the affected rule and does not create a
  finding;
- text and JSON totals agree;
- existing BurnRate usage and cost behavior is unchanged;
- the full test suite passes from an installed package;
- a twenty-day local scan completes and its top findings can be understood
  without reading an evidence schema.

## Simplicity budget

Treat these limits as design constraints for the first release:

- at most three new production modules;
- at most nine active rules;
- one result type and one aggregation path;
- no runtime dependencies;
- no persisted state or sidecar;
- no natural-language similarity;
- no score;
- no extension point until a second provider or genuinely different detector
  requires one.

If a proposed feature does not improve the default ranked report, defer it.
