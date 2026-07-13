# BurnRate Implementation Plan

Each unchecked item below is intended to be completed as one independently
mergeable pull request. Dependencies indicate merge order; PRs without a
dependency can be developed independently. Every PR must pass the complete
existing test suite plus its focused tests.

## High priority

### H1 - Treat missing Codex model metadata as unpriced

- [ ] Replace the `gpt-4o-mini` parser fallback with `UNKNOWN_MODEL`.
- [ ] Preserve token usage while setting the record cost to `None`.
- [ ] Report missing-model usage alongside other unpriced models.
- [ ] Test missing model metadata, absent `turn_context`, and a model supplied
  by `turn_context`.

Dependencies: none.

### H2 - Scope usage keys to sessions

- [ ] Deduplicate cumulative usage using `(session_id, request_id)` instead of
  request ID alone.
- [ ] Resolve session IDs from record metadata and then the source filename.
- [ ] Retain `session_id` and `request_id` in returned usage records.
- [ ] Test repeated request IDs within one session and identical request IDs
  across sessions and files.

Dependencies: none.

### H3 - Preserve records without request IDs or timestamps

- [ ] When a request ID is absent, use the resolved filepath and source line
  number as a unique identity.
- [ ] Do not use the timestamp alone as a fallback identity.
- [ ] Select duplicate cumulative records by parsed timestamp, using sorted
  filepath and line number as deterministic tie-breakers.
- [ ] Test missing request IDs, missing timestamps, repeated timestamps, and
  multiple identity-deficient records.

Dependencies: H2.

### H4 - Correct projections containing undated records

- [ ] Parse dates defensively and classify missing or invalid timestamps as
  undated.
- [ ] Include undated records in usage totals and known-cost totals.
- [ ] Exclude undated cost from the dated 30-day projection and report the
  number and known cost of excluded records.
- [ ] Mark the projection unavailable when no valid dated records exist.
- [ ] Test all-dated, mixed, all-undated, invalid-timestamp, and single-day
  scans.

Dependencies: none.

### H5 - Verify and document API pricing

- [ ] Verify every bundled rate against an authoritative provider source.
- [ ] Record the source URL, USD currency, rate unit, verification date, and
  effective date for every model rate.
- [ ] Label calculated cost as API-equivalent USD in documentation and output.
- [ ] State explicitly that BurnRate does not yet calculate Codex credit use.
- [ ] Preserve the existing `CODEX_PRICING`, `CLAUDE_PRICING`, and
  `calculate_cost()` imports.
- [ ] Test pricing metadata completeness, supported token categories, and
  unknown-model behavior.

Dependencies: H1.

### H6 - Report skipped and malformed records

- [ ] Count malformed JSON, non-object JSON, invalid record shapes, and
  unusable usage records by category.
- [ ] Print a concise diagnostic summary after parsing.
- [ ] Mark totals as potentially incomplete when usage-like records were
  rejected.
- [ ] Reset all diagnostic state at the beginning of every parse.
- [ ] Test each skip category, mixed valid and invalid files, and repeated
  parsing.

Dependencies: none.

### H7 - Validate nested structures and token values

- [ ] Confirm nested payloads are mappings before accessing them.
- [ ] Treat absent token fields as zero.
- [ ] Reject records containing supplied token values that are booleans,
  non-integers, or negative; do not coerce numeric strings.
- [ ] Test invalid payloads, lists instead of mappings, strings, floats,
  booleans, negative values, and valid zero values.

Dependencies: H6.

### H8 - Handle unreadable and undecodable files

- [ ] Catch per-file `OSError` and `UnicodeError` failures.
- [ ] Continue scanning other files after a failure.
- [ ] Print one concise, filepath-specific diagnostic for each affected file.
- [ ] Expose whether the scan was incomplete because a file could not be read.
- [ ] Test one failed file among valid files and a single unreadable input
  file.

Dependencies: H6.

## Medium priority

### M1 - Accept UTF-8 BOM files

- [ ] Read JSONL using `utf-8-sig`.
- [ ] Ensure the first record of ordinary UTF-8 and BOM-prefixed files is
  retained.
- [ ] Add BOM and non-BOM fixtures for both parsers.

Dependencies: none.

### M2 - Return meaningful CLI exit statuses

- [ ] Change `run()` to return an integer status.
- [ ] Exit `2` for an invalid top-level input path, `1` for an incomplete scan
  caused by file errors, and `0` for a complete scan.
- [ ] Continue to return `0` for reported malformed records when all input
  files were readable.
- [ ] Propagate the status through the console and module entry points.
- [ ] Test every exit path and existing parser dispatch behavior.

Dependencies: H8.

### M3 - Correct the build configuration

- [ ] Raise the build requirement to `setuptools>=61`.
- [ ] Declare `setuptools.build_meta` as the build backend.
- [ ] Add source-distribution, wheel, isolated-install, console-command, and
  module-command smoke tests.

Dependencies: none.

### M4 - Isolate parser tests

- [ ] Replace fixed repository-root mock directories with
  `TemporaryDirectory`.
- [ ] Ensure cleanup occurs even when a test fails.
- [ ] Preserve all existing behavioral coverage.

Dependencies: none.

### M5 - Add linting and formatting checks

- [ ] Configure Ruff for Python 3.9.
- [ ] Apply formatting as a dedicated mechanical change.
- [ ] Document lint and formatting-check commands for contributors.

Dependencies: M4.

### M6 - Add continuous integration

- [ ] Run unit tests on Python 3.9 and the latest stable Python available in
  GitHub Actions.
- [ ] Run Ruff checks and package-build smoke tests.
- [ ] Cache only safe dependency and build artifacts.

Dependencies: M3 and M5.

### M7 - Use one version source

- [ ] Make `pyproject.toml` authoritative for the package version.
- [ ] Expose the installed version through `importlib.metadata`.
- [ ] Provide a safe source-tree fallback when distribution metadata is
  unavailable.
- [ ] Test installed and source-tree version access.

Dependencies: M3.

### M8 - Complete package metadata

- [ ] Declare the MIT license, author, repository URL, issue tracker, and
  relevant package classifiers.
- [ ] Use the existing repository and license information.
- [ ] Validate the metadata through the built wheel.

Dependencies: M3.

### M9 - Synchronize README documentation

- [ ] Update the project tree to list all current modules and tests.
- [ ] Document parser diagnostics, partial costs, API-equivalent USD,
  projection exclusions, and CLI exit statuses.
- [ ] Verify every documented command against an installed package.

Dependencies: H4, H5, H6, M2, and M3.

## Low priority / structural improvements

### L1 - Introduce typed usage records

- [ ] Add typed `UsageRecord`, `UsageSummary`, and diagnostic dataclasses.
- [ ] Change internal aggregation to use typed records.
- [ ] Provide dictionary conversion for existing callers.
- [ ] Test construction, conversion, equality, and parser output.

Dependencies: all high-priority parser work.

### L2 - Split filesystem discovery from record parsing

- [ ] Create a shared discovery layer for validating inputs and finding sorted
  JSONL files.
- [ ] Keep provider-specific record interpretation inside each parser.
- [ ] Preserve current single-file and recursive-directory behavior.
- [ ] Test files, recursive directories, empty directories, invalid paths, and
  deterministic discovery order.

Dependencies: L1.

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

Dependencies: M2.

### L5 - Strengthen the `BaseParser` contract

- [ ] Retain `BaseParser` and type its parsing, summary, diagnostics, and input
  status contract.
- [ ] Move common state-reset behavior into a protected helper only where the
  implementations are identical.
- [ ] Test that both concrete parsers satisfy the contract and reset all shared
  state.

Dependencies: L1 and L3.

## Deferred to the product roadmap

- Context growth, cache share, replay ratio, and personal session baselines.
- Codex credit-equivalent estimates.
- Historical and versioned rate-card resolution and pricing update commands.
- Recommendations, budgets, exports, dashboards, and content-aware analysis.

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
