# BurnRate Historic Plan

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

## Product milestone 1a - Validate deterministic waste signatures (`v0.2.0`) — closed

Status: completed as a negative validation on 2026-08-02.

The privacy-bounded Codex structured-trace pilot delivered P1A-1 through
P1A-4. Ten live-log candidates were reviewed; none justified a workflow
change. The outcome is therefore that these deterministic signatures are not
promoted as validated actionable waste signals. The experiment remains
isolated and reversible, with no dependency on L1, L3, or a common-schema
refactor.

Residual operational work from P1A-5 (experimental CLI, offline/privacy
documentation, and broader session validation) continues in Product milestone
1b.
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
