# BurnRate Implementation Plan

Each unchecked item below is intended to be completed as one independently
mergeable pull request. Dependencies indicate merge order; PRs without a
dependency can be developed independently. Every PR must pass the complete
existing test suite plus its focused tests.

All High and Medium priority work is required for the v0.1.1 release. Low
priority work is not a v0.1.1 release blocker.

## High priority v0.1.1

### H1 - Treat missing Codex model metadata as unpriced

- [x] Replace the `gpt-4o-mini` parser fallback with `UNKNOWN_MODEL`.
- [x] Preserve token usage while setting the record cost to `None`.
- [x] Report missing-model usage alongside other unpriced models.
- [x] Test missing model metadata, absent `turn_context`, and a model supplied
  by `turn_context`.

Dependencies: none.

### H2A - Audit and correct API rates

- [x] Verify every bundled model and token-category rate against an
  authoritative provider source.
- [x] Correct stale rates and remove models or categories that cannot be
  verified confidently.
- [x] Keep the current provider dictionaries and `calculate_cost()` interface
  for this PR so rate corrections remain isolated from structural changes.
- [x] Remove inferred cache-rate multipliers; every priced token category must
  have an explicit verified rate.
- [x] Retain unknown or unverifiable models as unpriced instead of guessing.
- [x] Add exact calculation fixtures for every supported model and token
  category, including cache reads and cache writes.

Dependencies: H1.

### H2B - Add pricing provenance and API-equivalent labels

- [x] Add plain-dictionary metadata for source URL, USD currency, source and
  stored units, verification date, and effective-date status.
- [x] Record an explicit unknown status when an authoritative source does not
  publish an effective date; do not invent one.
- [x] Label calculated cost as API-equivalent USD in documentation and output.
- [x] State explicitly that estimates are not provider invoices and that
  BurnRate does not yet calculate Codex credit use.
- [x] Test metadata completeness and formatting for every priced model.

Dependencies: H2A.

### H3 - Scope usage keys to sessions

- [x] Deduplicate cumulative usage using `(session_id, request_id)` instead of
  request ID alone.
- [x] Resolve session IDs from record metadata and then the source filename.
- [x] Retain `session_id` and `request_id` in returned usage records.
- [x] Test repeated request IDs within one session and identical request IDs
  across sessions and files.

Dependencies: none.

### H4 - Preserve records without request IDs or timestamps

- [x] When a request ID is absent, use the resolved filepath and source line
  number as a unique identity.
- [x] Do not use the timestamp alone as a fallback identity.
- [x] Select duplicate cumulative records by parsed timestamp, using sorted
  filepath and line number as deterministic tie-breakers.
- [x] Test missing request IDs, missing timestamps, repeated timestamps, and
  multiple identity-deficient records.

Dependencies: H3.

### H5 - Correct projections containing undated records

- [x] Parse dates defensively and classify missing or invalid timestamps as
  undated.
- [x] Include undated records in usage totals and known-cost totals.
- [x] Exclude undated cost from the dated 30-day projection and report the
  number and known cost of excluded records.
- [x] Mark the projection unavailable when no valid dated records exist.
- [x] Test all-dated, mixed, all-undated, invalid-timestamp, and single-day
  scans.

Dependencies: H4.

### H6 - Report skipped and malformed records

- [x] Count malformed JSON, non-object JSON, invalid record shapes, and
  unusable usage records by category.
- [x] Print a concise diagnostic summary after parsing.
- [x] Mark totals as potentially incomplete when usage-like records were
  rejected.
- [x] Reset all diagnostic state at the beginning of every parse.
- [x] Test each skip category, mixed valid and invalid files, and repeated
  parsing.

Dependencies: none.

### H7 - Validate nested structures and token values

- [x] Confirm nested payloads are mappings before accessing them.
- [x] Treat absent token fields as zero.
- [x] Reject records containing supplied token values that are booleans,
  non-integers, or negative; do not coerce numeric strings.
- [x] Test invalid payloads, lists instead of mappings, strings, floats,
  booleans, negative values, and valid zero values.

Dependencies: H6.

### H8 - Handle unreadable and undecodable files

- [x] Catch per-file `OSError` and `UnicodeError` failures.
- [x] Continue scanning other files after a failure.
- [x] Print one concise, filepath-specific diagnostic for each affected file.
- [x] Expose whether the scan was incomplete because a file could not be read.
- [x] Test one failed file among valid files and a single unreadable input
  file.

Dependencies: H6.

### H9 - Validate cross-field token invariants

- [x] Reject Codex usage records where `cached_input_tokens` exceeds
  `input_tokens`; do not hide the inconsistency with clamping.
- [x] Reject records where supplied `reasoning_output_tokens` exceeds
  `output_tokens`.
- [x] When `total_tokens` is supplied, require it to equal `input_tokens` plus
  `output_tokens`; continue to allow the field to be absent.
- [x] Record rejected values as unusable usage and mark totals as potentially
  incomplete through the existing H6 diagnostics.
- [x] Preserve valid lower, equal, absent, and zero values for every invariant.
- [x] Test each boundary and mismatch for known and unknown models.

Dependencies: H6 and H7.

### H10 - Validate model and identity metadata

- [x] Accept non-empty string values for model, session ID, and request ID
  fields before using them in pricing lookups, sets, or dictionary keys.
- [x] Treat absent, `null`, and empty identity values as missing and use the
  existing deterministic fallbacks.
- [x] Preserve missing-model behavior as `UNKNOWN_MODEL` and unpriced.
- [x] Reject supplied booleans, numbers, lists, and mappings as invalid record
  shapes; do not stringify or otherwise coerce them.
- [x] Validate Codex `turn_context.model`, `info.model`, session IDs, and
  request IDs, plus the corresponding Claude message and top-level fields.
- [x] Mark rejected usage-like records as potentially incomplete through H6
  and continue parsing later records.
- [x] Test every invalid type, missing and empty values, and valid strings for
  both parsers.

Dependencies: H6 and H7.

### H11 - Make fallback session identities path-unique

- [x] Use the resolved source filepath, not only the filename stem, when
  explicit session metadata is absent.
- [x] Preserve valid explicit session metadata unchanged.
- [x] Keep returned fallback `session_id` values deterministic and
  string-valued.
- [x] Retain identical request IDs from files with the same basename in
  different directories while preserving deduplication within one file.
- [x] Add recursive-directory fixtures for both parsers and update existing
  filename-fallback assertions.

Dependencies: H3, H4, and H10.

### H12 - Consolidate hardening test coverage

- [x] Inventory the behavioral assertions added for H9 through H11 before
  refactoring, and preserve a direct test for every accepted value, rejected
  value, fallback, diagnostic, continuation, and deduplication contract.
- [x] Replace the duplicated Codex and Claude identity-type tests with one
  table-driven contract test using provider-specific record builders and
  `subTest` labels for provider, field, and invalid value.
- [x] Replace the duplicated missing, `null`, empty, and valid identity tests
  with one table-driven contract test while retaining explicit assertions for
  `UNKNOWN_MODEL`, unpriced usage, session precedence, request fallback, and
  string-valued session IDs.
- [x] Fold supplied `total_tokens` type cases into the existing Codex strict
  token-value test, while keeping cross-field arithmetic invariants in a
  separate focused test.
- [x] Remove the older distinct-basename fallback tests once the recursive
  same-basename fixtures cover resolved-path fallback, cross-directory
  retention, and within-file request deduplication for both parsers.
- [x] Share recursive fixture construction where it improves readability, but
  retain separately named Codex and Claude test entry points so failures remain
  provider-specific.
- [x] Do not change parser behavior, diagnostics, result schemas, or public
  interfaces as part of this refactor; production-code cleanup requires a
  separate reviewed item.
- [x] Record before-and-after test line counts, require a material reduction in
  duplicated setup and assertions without introducing opaque test helpers, and
  run the complete test suite plus `git diff --check`.

Dependencies: H9, H10, and H11.

Result: the three affected test files decreased from 1,614 to 1,520 lines
(-94, 5.8%) while retaining the H9-H11 behavioral contracts. The full suite
passes with 59 tests.

## Medium priority v0.1.1

### M1 - Accept UTF-8 BOM files

- [x] Read JSONL using `utf-8-sig` so a leading UTF-8 BOM is consumed without
  changing ordinary UTF-8 behavior.
- [x] Ensure the first record of ordinary UTF-8 and BOM-prefixed files is
  retained by both parsers.
- [x] Add single-file and directory-scan fixtures for BOM and non-BOM input.
- [x] Confirm BOM handling does not change malformed-record or file-read
  diagnostics.

Dependencies: H6 and H8.

### M2 - Handle filesystem discovery failures

- [x] Catch `OSError` failures from top-level path inspection and recursive
  JSONL discovery, not only failures raised while reading an individual file.
- [x] Distinguish an invalid top-level input from a partially completed
  directory scan so M3 can return the correct status.
- [x] Preserve results from files successfully discovered and parsed before a
  later discovery failure, while marking the scan incomplete.
- [x] Print one concise, path-specific diagnostic for each inspection or
  discovery failure without a traceback.
- [x] Reset discovery-error state at the start of every parse.
- [x] Test missing paths, inspection failures, enumeration failures after
  successful files, empty directories, and repeated parsing for both parsers.

Dependencies: H8.

### M3 - Return meaningful CLI exit statuses

- [x] Change `run()` to return an integer status while preserving parser
  selection, output, and direct Python usage.
- [x] Exit `2` for an invalid top-level input path, `1` for an incomplete scan
  caused by file or discovery errors, and `0` for a complete scan.
- [x] Continue to return `0` for reported malformed records when all input
  files were readable and discovery completed.
- [x] Propagate the status through the console entry point,
  `python -m burnrate`, and direct `burnrate.main.run()` calls.
- [x] Test every exit path for both parsers plus existing argument-dispatch
  behavior.

Dependencies: H8 and M2.

### M4 - Correct the build configuration

- [x] Raise the build requirement to `setuptools>=61`.
- [x] Declare `setuptools.build_meta` as the build backend.
- [x] Restrict package discovery to `burnrate` so repository support
  directories cannot be included as top-level packages.
- [x] Add source-distribution, wheel, isolated-install, console-command, and
  module-command smoke tests.

Dependencies: none.

### M5 - Use one version source

- [x] Make `pyproject.toml` authoritative for the package version.
- [x] Expose the installed version through `importlib.metadata`.
- [x] Provide a safe source-tree fallback when distribution metadata is
  unavailable.
- [x] Test installed and source-tree version access.

Dependencies: M4.

### M6 - Synchronize README documentation

- [x] Update the project tree to list all current modules and tests.
- [x] Document parser diagnostics, partial costs, API-equivalent USD,
  projection exclusions, BOM handling, conditional-pricing assumptions,
  unpriced conditional records, incomplete scans, and CLI exit statuses.
- [x] Verify every documented command against an installed package.

Dependencies: all High priority work plus M1 through M5.

### M7 - Prepare and verify the v0.1.1 release

- [x] Complete the pre-release cleanup audit: reduce filesystem diagnostics to
  the status flags consumed by the CLI, remove dead Claude extraction helpers,
  and simplify the Codex event guard without changing parser behavior.
- [x] Add a concise README summary of the v0.1.1 changes and known limitations.
- [x] Set the authoritative package version to `0.1.1`.
- [x] Run the complete test suite against the supported Python versions.
- [x] Build the source distribution and wheel, install the wheel in an
  isolated environment, and run console-command and module-command smoke
  tests.
- [x] Confirm installed and source-tree version reporting both return
  `0.1.1`.
- [x] Confirm the release verification leaves no tracked generated artifacts
  or undocumented user-facing behavior.
- [x] Prepare a v0.1.1 change summary covering parser correctness, pricing
  assumptions, diagnostics, CLI statuses, and known limitations.

Dependencies: M6.

## High priority next release: deterministic waste-signature pilot (v0.2.0)

This is the next implementation priority after v0.1.1. It validates
BurnRate's execution-intelligence proposition without reading natural-language
message bodies or calling another LLM. All source logs remain read-only.

### P1A-1 - Add a Codex structured-trace reader and fixtures

- [x] Add an experimental, provider-specific Codex event reader separate from
  the existing token-and-cost parser; do not refactor the v0.1.1 parser path.
- [x] Retain only structured event fields required for the pilot: session and
  agent lineage, timestamp, event type, token snapshot, tool name, command,
  path, exit status, error text, and patch/mutation status.
- [x] Explicitly discard natural-language user, agent, and reasoning bodies.
- [x] Add representative anonymized fixtures covering tool calls, tool outputs,
  token counts, patches, failed commands, and absent or malformed fields.
- [x] Add focused tests proving message bodies are not retained in the
  experimental result.

Dependencies: v0.1.1 release verification.

### P1A-2 - Add deterministic normalization and evidence signatures

- [x] Normalize commands, paths, volatile IDs, timestamps, exit statuses, and
  error text into stable, inspectable signatures.
- [x] Classify structured operations as discovery, read, test, mutation,
  authentication, version-control, or unknown using explicit rules.
- [x] Preserve raw source location and normalized values so every result can
  be traced and challenged.
- [x] Add exact-match and volatile-value normalization tests; do not use
  embeddings or an LLM.

Dependencies: P1A-1.

### P1A-3 - Detect deterministic waste signatures

- [x] Produce preliminary execution-pattern candidates for repeated commands,
  repeated discovery, token-before-mutation, recurring failures, and possible
  duplicate subagent work; do not present these candidates as waste findings.
- [x] Parse Codex's execution-outcome envelope only far enough to retain exit
  status and a normalized failure fingerprint, then discard its raw body.
- [x] Extract read targets only from recognized structured tool arguments or
  conservative command forms; retain the path but never source-file content.
- [x] Detect potentially avoidable repetition only when the same read,
  successful command, failed command, or complete repository discovery occurs
  without an observed relevant mutation in between. State the result as "no
  observed mutation", not proof that no external change occurred.
- [x] Attribute token snapshots to the timeline and calculate tokens consumed
  before the first observed successful repository mutation; label the result
  as orientation evidence rather than waste until a validated intervention
  shows it is avoidable.
- [x] Detect probable duplicated subagent work only when explicit lineage plus
  timing, command, path, or patch-overlap evidence supports it; leave the
  result unavailable when lineage is absent.
- [x] Label every result as observed, derived, heuristic, or unavailable and
  include an explicit confidence rule rather than a composite score. Missing
  exit status, mutation, lineage, or task-grouping evidence is unavailable,
  never a negative finding.
- [x] Add privacy-safe fixtures for successful and failed non-JSON outcome
  envelopes, repeated reads, unchanged retries, and mutation boundaries, with
  focused assertions that raw bodies are not retained.
- [x] Manually review at least ten live-log candidates and record whether each
  changes a real workflow decision before calling these patterns validated
  waste signatures.

- [x] Add deterministic automation-failure episodes that correlate run overlap,
  checkpoint/import rejection, stale paths, schema/query errors, shell quoting
  failures, interrupted runs, and misleading successful terminal status.
- [x] Store only normalized episode signatures, operation, exit status, error
  fingerprint, timing, recovery, terminal outcome, and source locations; never
  retain Gmail IDs, message bodies, email addresses, or raw tool output.
- [x] Add anonymized fixtures and live-log review tests proving failure episodes
  remain traceable without exposing provider identifiers or natural-language content.

Dependencies: P1A-2.

### P1A-4 - Produce a local report, sidecar, and instruction candidates

- [x] Add deterministic JSON and Markdown renderers for the pilot result.
- [x] Include evidence locations, derivation, confidence, and missing-evidence
  labels for every finding.
- [x] Add a versioned local sidecar for user confirmations, corrections,
  categories, outcomes, and notes.
- [x] Generate suggested AGENTS.md, project-memory, cache-entry, or skill
  text from deterministic templates; never write those targets automatically.
- [x] Add redaction-safe fixtures and tests for report and sidecar stability.

Dependencies: P1A-3.

### P1A-5 - Add an experimental CLI and validate the pilot

- [ ] Add an explicit experimental CLI command and input-path option while
  preserving all existing CLI behavior.
- [ ] Keep analysis offline and make content analysis unavailable in this
  release.
- [ ] Document the evidence boundary, privacy behavior, limitations, and exact
  meaning of “first observed successful repository mutation”.
- [ ] Validate on at least ten local tasks or sessions, record whether a
  finding changes a real workflow decision, and publish no claims beyond the
  observed evidence.

Dependencies: P1A-4.

## Low priority / structural improvements v0.1.x

### L1 - Introduce typed usage records

- [ ] Add typed `UsageRecord`, `UsageSummary`, and diagnostic dataclasses.
- [ ] Change internal aggregation to use typed records.
- [ ] Provide dictionary conversion for existing callers.
- [ ] Test construction, conversion, equality, and parser output.

Dependencies: all high-priority parser work.

### L2 - Split filesystem discovery from record parsing

- [ ] Extract the validated M2 discovery behavior into a shared layer for
  input validation and deterministic JSONL discovery.
- [ ] Keep provider-specific record interpretation inside each parser.
- [ ] Preserve current single-file and recursive-directory behavior.
- [ ] Test files, recursive directories, empty directories, invalid paths, and
  deterministic discovery order.

Dependencies: M2 and L1.

### L3 - Separate aggregation from console rendering

- [ ] Make aggregation a pure operation over usage records.
- [ ] Build console output from `UsageSummary`.
- [ ] Preserve `parser.summary()` as a compatibility wrapper during the 0.x
  series.
- [ ] Test aggregation without stdout and add focused renderer assertions.

Dependencies: L1.

### L4 - Rename the CLI module

- [ ] Move the CLI implementation from `burnrate/main.py` to
  `burnrate/cli.py`.
- [ ] Update package and console entry points.
- [ ] Retain `burnrate.main` as a compatibility re-export during the 0.x
  series.
- [ ] Test the old import, new import, console command, and module execution.

Dependencies: M3.

### L5 - Strengthen the `BaseParser` contract

- [ ] Retain `BaseParser` and type its parsing, summary, diagnostics, and input
  status contract.
- [ ] Move common state-reset behavior into a protected helper only where the
  implementations are identical.
- [ ] Test that both concrete parsers satisfy the contract and reset all shared
  state.

Dependencies: L1 and L3.

### L6 - Isolate parser tests

- [ ] Replace fixed repository-root mock directories with
  `TemporaryDirectory`.
- [ ] Ensure cleanup occurs even when a test fails.
- [ ] Preserve all existing behavioral coverage.

Dependencies: none.

### L7 - Add linting and formatting checks

- [ ] Configure Ruff for Python 3.9.
- [ ] Apply formatting as a dedicated mechanical change.
- [ ] Document lint and formatting-check commands for contributors.

Dependencies: L6.

### L8 - Add continuous integration

- [ ] Run unit tests on Python 3.9 and the latest stable Python available in
  GitHub Actions.
- [ ] Run Ruff checks and package-build smoke tests.
- [ ] Cache only safe dependency and build artifacts.

Dependencies: M4 and L7.

### L9 - Complete package metadata

- [ ] Declare the MIT license, author, repository URL, issue tracker, and
  relevant package classifiers.
- [ ] Use the existing repository and license information.
- [ ] Validate the metadata through the built wheel.

Dependencies: M4.

### L10 - Unify the API pricing structure

- [ ] Replace the provider-specific pricing dictionaries with one plain nested
  `API_PRICING` mapping; do not introduce pricing dataclasses.
- [ ] Store source-facing rates per million tokens so values can be compared
  directly with provider rate cards.
- [ ] Rename `calculate_cost()` to `calculate_api_cost()` and update both
  parsers and all tests.
- [ ] Remove the obsolete `CODEX_PRICING`, `CLAUDE_PRICING`, and parser-level
  `PRICING` aliases.
- [ ] Keep pricing data, provenance, and effective-date information together
  so they cannot drift independently.

Dependencies: L14, L15, and L16.

### L11 - Estimate Codex credit-equivalent usage

- [ ] Add a separate `CODEX_CREDIT_PRICING` rate card; never mix credit rates
  with API-equivalent USD rates.
- [ ] Calculate estimated credits independently from input, cached-input, and
  output token counts.
- [ ] Record the authoritative source URL, credit unit, verification date, and
  effective date for every supported model rate.
- [ ] Report API-equivalent USD and Codex credit-equivalent usage in separate
  columns and totals.
- [ ] Mark credit estimates unavailable for unsupported models or when the
  applicable rate-card conditions cannot be established.
- [ ] Warn when fast mode, legacy Enterprise pricing, or other missing log
  metadata could make actual credit consumption differ from the estimate.
- [ ] Test every supported model, token category, and incomplete-estimate path.

Dependencies: H2B.

### L12 - Investigate a Claude retail-plan usage proxy

- [ ] Treat Claude Pro and Max included usage as opaque; do not invent a
  token-to-credit conversion, allowance percentage, or remaining balance.
- [ ] Retain API-equivalent USD as a workload-intensity proxy and label it
  explicitly as distinct from retail-plan allowance consumption.
- [ ] Determine whether Claude Code logs expose reliable authentication,
  billing-mode, or provider-reported usage-limit metadata before adding any
  stronger estimate.
- [ ] Report retail allowance usage as unavailable when the applicable plan or
  conversion cannot be established from authoritative data.
- [ ] Document the limitation and test proxy labeling and unavailable paths.

Dependencies: H2B and L11.

### L13 - Extract small shared parser helpers

- [ ] Extract identical token validation, timestamp selection-order, folder
  aggregation, and dated-projection calculations into focused protected
  helpers.
- [ ] Keep provider-specific record shapes, usage extraction, pricing inputs,
  and summary columns in the concrete parsers.
- [ ] Do not introduce a generic `_parse_file()` workflow or a parser
  framework that obscures the Codex and Claude control flow.
- [ ] Preserve existing parser attributes, console output, diagnostics, and
  dictionary-based return values.
- [ ] Measure the reduction in duplicated code and retain focused regression
  coverage for every extracted helper.

Dependencies: H5, H6, and H9. Coordinate with L3 and L5 to avoid duplicate
work.

### L14 - Add Claude cache-duration pricing

- [ ] Parse Claude cache-creation duration breakdowns and price 5-minute and
  1-hour writes independently using explicit provider-published rates.
- [ ] Confirm `cache_creation_input_tokens` equals the sum of the supplied
  5-minute and 1-hour breakdown; reject inconsistent records.
- [ ] Keep cache creation unpriced when a nonzero total lacks the duration
  breakdown required to select a rate confidently.
- [ ] Preserve the current provider dictionaries and `calculate_cost()`
  interface in this PR so pricing correctness remains isolated from L10.
- [ ] Add 5-minute-only, 1-hour-only, mixed-duration, absent-breakdown, zero,
  and inconsistent-total fixtures for every supported Claude model.
- [ ] Cross-check fixtures against ccusage behavior while keeping authoritative
  provider rate cards as the source of pricing truth.

Dependencies: H2B.

### L15 - Add OpenAI long-context pricing

- [ ] Record explicit provider-published long-context thresholds and rates for
  supported OpenAI models; do not infer rates for other models.
- [ ] Apply whole-request long-context pricing when input exceeds the model's
  published threshold, including input, cached-input, and output categories.
- [ ] Keep unsupported or ambiguous long-context records unpriced instead of
  applying standard rates confidently.
- [ ] Preserve the current provider dictionaries and `calculate_cost()`
  interface in this PR so pricing correctness remains isolated from L10.
- [ ] Add fixtures immediately below, at, and above every supported threshold,
  including cached-input and output calculations.

Dependencies: H2B and H9.

### L16 - Add Claude conditional and long-context pricing

- [ ] Audit which long-context, inference-geography, platform, batch, and other
  pricing-condition fields are retained reliably in Claude Code logs.
- [ ] Apply provider-documented Claude long-context pricing using the correct
  threshold and marginal or whole-request semantics for each supported model.
- [ ] Apply supported geography or platform modifiers only when the required
  log metadata establishes them unambiguously.
- [ ] Keep usage unpriced when a material pricing condition cannot be
  established from the log; state the API-equivalent assumptions explicitly.
- [ ] Preserve the current provider dictionaries and `calculate_cost()`
  interface in this PR so pricing correctness remains isolated from L10.
- [ ] Add boundary fixtures plus global, US-only, missing-condition, and
  unsupported-platform fixtures for every affected model.
- [ ] Cross-check fixtures against ccusage behavior while keeping authoritative
  provider rate cards as the source of pricing truth.

Dependencies: H2B and L14.

## Deferred to the product roadmap

The existing v0.1.1 parser, pricing, diagnostics, packaging, and test
foundation should be extended through the following milestone sequence. These
milestones describe one local product with an optional simple cloud execution
path; they do not commit BurnRate to becoming a SaaS product.

Proposed versions are provisional and scope-driven rather than date-driven:

| Stage | Proposed version | Release meaning |
| --- | --- | --- |
| Current baseline | `v0.1.1` | Hardened local provider-specific CLI |
| Product milestone 1a | `v0.2.0` | Deterministic local waste-signature validation |
| Product milestone 1b | `v0.2.1` | Opt-in message-content intelligence validation |
| Product milestone 2 | `v0.3.0` | Reusable typed analysis boundary informed by the pilot |
| Product milestone 3 | `v0.3.1` | Unified local analysis and deterministic JSON |
| Product milestone 4 | `v0.3.2` | Self-contained HTML and redacted export bundles |
| Product milestone 5 | `v0.4.0` | Supported local task-level execution intelligence |
| Product milestone 6 | `v0.5.0` | Optional ephemeral AWS processing preview |
| Product milestone 7 | `v0.5.1` | Portfolio, operational, and release hardening |

`v1.0.0` remains unassigned. It should follow demonstrated user value, a
stable local workflow and data schema, documented compatibility guarantees,
and repeatable release evidence; it does not require a SaaS product.

### Product milestone 1a - Validate deterministic waste signatures (`v0.2.0`)

This high-priority pilot tests the privacy-preserving version of the product
idea before BurnRate commits to a broad analysis-engine refactor. It uses
structured traces only, does not inspect natural-language message bodies, and
does not call another LLM. Provider-specific experimental code is acceptable
when it keeps validation work small and reversible.

- [x] Start with Codex structured traces; add the second provider only if it
  answers a validation question that Codex cannot.
- [ ] Read provider logs without modifying them and extract the minimum
  session, request, timestamp, model, token, cost, retry, error, and tool-use
  evidence that the source actually exposes.
- [ ] Infer task boundaries, but allow the user to confirm, split, merge, or
  rename inferred tasks.
- [ ] Store task corrections, categories, outcomes, and notes in a separate
  local sidecar file with an explicitly experimental schema version.
- [ ] Support successful, partial, failed, abandoned, and unknown outcomes
  without treating cost or speed as a proxy for success.
- [ ] Generate a simple deterministic JSON or Markdown report that compares
  transparent task metrics; do not create a composite efficiency or
  model-quality score.
- [x] Mark every reported value as observed, derived, user-supplied,
  heuristically inferred, or unavailable where that distinction matters.
- [x] Record whether each report observation changes or informs a concrete
  model, prompting, context, tool, or task-decomposition decision.

Completion criteria:

- Source logs remain read-only and all user-authored task metadata lives in an
  inspectable sidecar.
- A representative local set of at least ten tasks includes successful and
  unsuccessful or partial outcomes.
- The user can correct task grouping and label outcomes without editing source
  logs.
- Every metric exposes its evidence and labels unavailable evidence instead of
  converting it to zero.
- At least one report observation changes or informs a real workflow decision.
- If the experiment does not produce actionable signal, it can be revised or
  removed without first completing L1, L3, or a common-schema refactor.

### Product milestone 1b - Validate opt-in content intelligence (`v0.2.1`)

Start only when 1a demonstrates value and a specific unanswered question
requires natural-language content. It is disabled by default, local and
inspectable, and begins with deterministic text analysis rather than another
LLM.

- [ ] Read only the selected minimum user and agent message bodies and report
  exactly which fields were inspected.
- [ ] Identify repeated investigative questions and similar work using
  deterministic matching and similarity measures with user-reviewable evidence.
- [ ] Produce low-confidence, user-confirmable candidates for scope drift,
  overengineering, semantic subagent duplication, and recurring knowledge.
- [ ] Keep any LLM-assisted classifier or synthesis as an optional, separately
  measured adapter that can be compared to and disabled from the deterministic
  baseline.

Completion criteria:

- Content analysis is disabled by default and its findings are distinguished
  from structured-trace findings.
- Users can inspect, correct, or reject every message-derived candidate.
- At least one message-derived finding supplies actionable signal that 1a
  could not produce; otherwise it is not promoted into the supported path.
- No instruction, memory, cache, or skill file is changed without approval.

### Product milestone 2 - Complete the reusable analysis boundary (`v0.3.0`)

Start this milestone only after the v0.2.0 experiment demonstrates useful
deterministic signal. Incorporate v0.2.1 findings only if opt-in content
analysis supplies additional actionable value. The pilots should determine the
durable record granularity, provenance, evidence-availability, task identity,
outcome, waste-signature, and pricing fields instead of designing them
speculatively.

Before the broad extraction, complete L6 through L9 so isolated tests, Ruff,
CI, package checks, and distribution metadata protect the refactor. These
delivery guardrails should not block iteration on the v0.2.0 experiment.

- [ ] Build on L1 to define a versioned typed and serializable common record,
  summary, diagnostic, and analysis-result schema while preserving dictionary
  conversion.
- [ ] Preserve provider, session and request identity, source location,
  timestamp validity, model and token categories, pricing completeness,
  rate-card identity, evidence provenance, and optional provider metadata
  where the validated workflow requires them.
- [ ] Build on L3 to move aggregation into a pure operation over common
  records and make console rendering a presentation adapter.
- [ ] Return structured file and record diagnostics from the reusable path
  instead of requiring parser-side printing.
- [ ] Add one application-service entry point that can analyse either or both
  providers from explicit paths without invoking the CLI.
- [ ] Keep existing parser methods, dictionary conversion, and console behavior
  as compatibility surfaces throughout the extraction.

Completion criteria:

- All existing tests remain green and current CLI output remains compatible.
- Both parsers convert their existing results to the versioned common schema.
- Parsing and aggregation can complete without writing to stdout.
- The validated task-intelligence evidence requirements are represented
  without pretending provider-specific evidence is universal.
- The CLI, local report generators, task workflow, and later Lambda worker can
  call the same application-service entry point.

### Product milestone 3 - Add unified analysis and deterministic JSON (`v0.3.1`)

- [ ] Auto-detect and analyse both Claude Code and Codex logs in one
  invocation while retaining explicit provider and path selection.
- [ ] Generate deterministic, versioned JSON alongside the existing console
  output.
- [ ] Keep provider asymmetry, missing evidence, pricing completeness, source
  provenance, and diagnostics explicit in the JSON contract.

Completion criteria:

- One command analyses both supported sources.
- Existing provider-specific commands remain compatible.
- Console and JSON totals agree for the same input.
- Repeated analysis of the same inputs produces equivalent JSON.
- The workflow remains offline and makes no network requests.

### Product milestone 4 - Add HTML and redacted exports (`v0.3.2`)

- [ ] Generate a self-contained local HTML view from the same versioned
  analysis result used by JSON and console rendering.
- [ ] Add local redaction, an inspectable export manifest, and a versioned
  diagnostic bundle.
- [ ] Keep report generation independent of provider-log parsing and
  aggregation.

Completion criteria:

- Console, JSON, and HTML outputs agree for the same input.
- The HTML report is self-contained and works offline.
- Users can inspect exactly which fields an exported bundle contains.
- Redaction and export tests cover representative sensitive fields and missing
  evidence.

### Product milestone 5 - Productize validated task intelligence (`v0.4.0`)

- [ ] Move the validated task-grouping and outcome workflow onto the reusable
  analysis boundary without silently changing its meaning.
- [ ] Support both providers where their observed evidence permits it and keep
  provider-specific limitations explicit.
- [ ] Calculate task cost, failed-effort cost, retries, context churn, tool use,
  and other efficiency metrics only where supported by observed log data.
- [ ] Generate explainable recommendations linked to observations, assumptions,
  and confidence instead of introducing speculative model-quality scoring.
- [ ] Define compatibility or migration behavior for experimental v0.2.0
  sidecars before declaring the workflow supported.
- [ ] Test the supported workflow and report with a small group of Claude Code
  and Codex users before building the optional cloud path.

Completion criteria:

- Every recommendation exposes its supporting evidence, assumptions, and
  confidence.
- Missing or unavailable evidence is labelled rather than inferred.
- At least three pilot users complete the local task-and-outcome workflow and
  provide structured feedback.
- Pilot users demonstrate that the report changes or informs an agent workflow
  decision.
- The cloud implementation is not started until the supported local report
  demonstrates sufficient user value.

### Product milestone 6 - Add a simple ephemeral AWS implementation (`v0.5.0`)

- Host a minimal static upload page using S3 and CloudFront.
- Use an API Gateway HTTP API with a small FastAPI application on Lambda.
- Upload files directly to S3 with short-lived presigned URLs.
- Queue parsing through SQS and process jobs with a Python Lambda worker that
  imports the shared BurnRate analysis engine.
- Store temporary job state and generated JSON or HTML reports in S3; do not
  introduce a database until a demonstrated requirement exists.
- Define the infrastructure with Terraform and deploy it through GitHub
  Actions using AWS OIDC.
- Add least-privilege IAM, managed encryption, strict upload limits, API
  throttling, reserved Lambda concurrency, lifecycle deletion, a dead-letter
  queue, focused CloudWatch alarms, and AWS Budget alerts.

Completion criteria:

- Upload, validation, queueing, parsing, report generation, and download work
  as one vertical production flow.
- The validated local task-level report is available through the cloud path
  without expanding its product scope.
- Local and cloud execution produce equivalent reports for the same input.
- Failed jobs are observable and recoverable through the dead-letter queue.
- Raw uploads and reports are deleted automatically after short configured
  retention periods.
- The deployment has no always-on compute, load balancer, NAT Gateway, or
  database cost.

This milestone is an optional cloud implementation of the validated local
utility, not a SaaS release. User accounts, subscriptions, team workspaces,
billing, multi-tenancy, and long-term hosted history are outside its scope.

### Product milestone 7 - Harden the portfolio implementation (`v0.5.1`)

- Document the architecture, data flow, local/cloud privacy boundary, threat
  model, cost model, and major architecture decisions.
- Treat the L6 through L9 guardrails as the baseline and add release evidence
  plus cloud-specific quality checks.
- Add contract tests, representative anonymized fixtures, failure-path tests,
  and cloud/local report-equivalence tests.
- Document service objectives, alarms, retry and dead-letter behavior,
  rollback, automatic deletion, and the operational runbook.
- Publish an anonymized example report, pilot findings, and measured cloud
  cost and performance.

Completion criteria:

- The repository can be built, tested, deployed, operated, and removed by
  following its documentation.
- Security, reliability, privacy, and cost decisions are represented by
  testable controls.
- Portfolio and CV claims remain limited to implemented and verified
  capabilities.

## Possible future directions

The following ideas are not committed releases. They describe possible SaaS,
team, or enterprise directions only if the local product and optional cloud
preview demonstrate demand.

- Position BurnRate as the FinOps and cost-intelligence layer for AI coding
  agents: explain and govern the economics of AI software development rather
  than becoming a general-purpose enterprise AI control plane.
- Add an organisation-aware usage ledger with accounts, teams, developers or
  devices, repositories or projects, providers, agents, sessions, models,
  cost centres, pricing versions, and completeness status as first-class
  dimensions.
- Support privacy-preserving local collectors and scheduled aggregation across
  machines, sending usage metadata by default without prompts, source code, or
  generated content.
- Build team reporting around cost-driver attribution, reporting-device
  coverage, forecasts, budgets, anomaly alerts, and deterministic CSV, JSON,
  accounting, and data-warehouse exports.
- Add enterprise controls only after the ledger is stable: SSO/SAML, role-based
  access, retention policies, audit logs, regional or self-hosted deployment,
  webhooks, cost-centre mapping, and policy integrations.
- Audit-grade cost build-up waterfalls, period-over-period driver attribution,
  counterfactual pricing scenarios, and confidence or coverage indicators for
  every explanation.
- Privacy-preserving, tokenhabit-style efficiency diagnostics for context
  growth, compaction overruns, repeated reads, output floods, cache-disrupting
  behavior, and other measurable usage patterns; keep heuristic waste estimates
  and recommendations clearly separate from exact accounting results.
- Personal session baselines and anomaly detection across cost and efficiency
  metrics.
- Historical and versioned rate-card resolution and pricing update commands.
- Recommendations, dashboards, and opt-in content-aware analysis.

## Completed work

- [x] Fix the monthly cost projection to account for the actual log date
  range.
- [x] Stop double-charging Codex reasoning tokens.
- [x] Handle unknown models explicitly instead of applying fallback pricing.
- [x] Repair test imports and test discovery; use `burnrate.parsers.*`.
- [x] Align the declared Python version with `list[dict]` usage using Python
  3.9 or newer.
- [x] Reset parser state before path validation and early returns.
- [x] Add pricing, caching, reasoning, and unknown-model regression tests.
- [x] Add malformed JSONL handling and tests.
- [x] Expand repeated-parsing and state-reset tests.
- [x] Add CLI argument and dispatch tests.
- [x] Fix README commands and remove references to the nonexistent root
  `main.py`.
- [x] Move pricing tables and cost calculations into `pricing.py`.
- [x] Ensure generated directories such as `burnrate.egg-info` and
  `__pycache__` remain ignored and untracked.
