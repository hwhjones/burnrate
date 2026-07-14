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

- [ ] When a request ID is absent, use the resolved filepath and source line
  number as a unique identity.
- [ ] Do not use the timestamp alone as a fallback identity.
- [ ] Select duplicate cumulative records by parsed timestamp, using sorted
  filepath and line number as deterministic tie-breakers.
- [ ] Test missing request IDs, missing timestamps, repeated timestamps, and
  multiple identity-deficient records.

Dependencies: H3.

### H5 - Correct projections containing undated records

- [ ] Parse dates defensively and classify missing or invalid timestamps as
  undated.
- [ ] Include undated records in usage totals and known-cost totals.
- [ ] Exclude undated cost from the dated 30-day projection and report the
  number and known cost of excluded records.
- [ ] Mark the projection unavailable when no valid dated records exist.
- [ ] Test all-dated, mixed, all-undated, invalid-timestamp, and single-day
  scans.

Dependencies: H4.

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

## Medium priority v0.1.1

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

### M4 - Use one version source

- [ ] Make `pyproject.toml` authoritative for the package version.
- [ ] Expose the installed version through `importlib.metadata`.
- [ ] Provide a safe source-tree fallback when distribution metadata is
  unavailable.
- [ ] Test installed and source-tree version access.

Dependencies: M3.

### M5 - Synchronize README documentation

- [ ] Update the project tree to list all current modules and tests.
- [ ] Document parser diagnostics, partial costs, API-equivalent USD,
  projection exclusions, and CLI exit statuses.
- [ ] Verify every documented command against an installed package.

Dependencies: all High priority work and M1 through M4.

### M6 - Prepare and verify the v0.1.1 release

- [ ] Set the authoritative package version to `0.1.1`.
- [ ] Run the complete test suite against the supported Python versions.
- [ ] Build the source distribution and wheel, install the wheel in an
  isolated environment, and run console-command and module-command smoke
  tests.
- [ ] Confirm installed and source-tree version reporting both return
  `0.1.1`.
- [ ] Confirm the release verification leaves no tracked generated artifacts
  or undocumented user-facing behavior.

Dependencies: M5.

## Low priority / structural improvements v0.1.x

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

Dependencies: M3 and L7.

### L9 - Complete package metadata

- [ ] Declare the MIT license, author, repository URL, issue tracker, and
  relevant package classifiers.
- [ ] Use the existing repository and license information.
- [ ] Validate the metadata through the built wheel.

Dependencies: M3.

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

Dependencies: H2B.

### L11 - Add duration-aware cache and long-context pricing

- [ ] Parse Claude cache-creation duration breakdowns and price 5-minute and
  1-hour writes independently using explicit provider-published rates.
- [ ] Apply OpenAI whole-request long-context rates when a supported model's
  input exceeds its published threshold, including the corresponding input,
  cached-input, and output rates.
- [ ] Apply provider-documented Claude long-context pricing with the correct
  threshold and marginal or whole-request semantics for each supported model.
- [ ] Keep usage unpriced when the log lacks information required to choose a
  pricing tier or cache duration confidently.
- [ ] Add boundary fixtures immediately below, at, and above every supported
  threshold, plus mixed 5-minute and 1-hour cache-write fixtures.
- [ ] Cross-check calculation fixtures against ccusage behavior while keeping
  authoritative provider rate cards as the source of pricing truth.
- [ ] Do not add dynamic pricing downloads, fuzzy model matching, inferred
  cache multipliers, or provider-reported invoice costs in this change.

Dependencies: L10.

### L12 - Estimate Codex credit-equivalent usage

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

### L13 - Investigate a Claude retail-plan usage proxy

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

Dependencies: H2B and L12.

## Deferred to the product roadmap

- Context growth, cache share, replay ratio, and personal session baselines.
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
