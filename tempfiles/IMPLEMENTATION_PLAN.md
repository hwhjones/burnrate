# BurnRate Implementation Plan

This is the active plan. Completed work, including the closed Product
Milestone 1a negative validation, is archived in
[`HISTORIC_PLAN.md`](HISTORIC_PLAN.md).

The product roadmap states outcomes and sequencing. The sprint-planning backlog
below contains implementation work that may be pulled into a milestone when its
dependency and validation gates are satisfied.

## Product roadmap

BurnRate will scaffold content-aware waste analysis on the existing structured
trace reader, normalizer, analyzer, sidecar, and report. Milestones 1b through
1e remain local and deterministic: no external LLM call is required or allowed.
Every finding must retain source evidence, state its derivation, and remain
user-reviewable.

Proposed versions are provisional and scope-driven rather than date-driven:

| Stage | Proposed version | Release meaning |
| --- | --- | --- |
| Product milestone 1b | `v0.2.1` | Opt-in content evidence in the existing trace stream |
| Product milestone 1c | `v0.2.2` | Deterministic message-to-execution correlation |
| Product milestone 1d | `v0.2.3` | Expanded rule catalog and meaningful-insight validation |
| Product milestone 1e | `v0.2.4` | Operationalize validated insights through the experimental CLI |
| Product milestone 2 | `v0.3.0` | Reusable typed analysis boundary informed by the pilots |
| Product milestone 3 | `v0.3.1` | Unified local analysis and deterministic JSON |
| Product milestone 4 | `v0.3.2` | Self-contained HTML and redacted export bundles |
| Product milestone 5 | `v0.4.0` | Supported local task-level execution intelligence |
| Product milestone 6 | `v0.5.0` | Optional ephemeral AWS processing preview |
| Product milestone 7 | `v0.5.1` | Portfolio, operational, and release hardening |

`v1.0.0` remains unassigned. It should follow demonstrated user value, a
stable local workflow and data schema, documented compatibility guarantees,
and repeatable release evidence; it does not require a SaaS product.

### Product milestone 1b - Add opt-in content evidence to structured traces (`v0.2.1`)

Extend the existing trace pipeline rather than creating a parallel content
product. Content interrogation is explicit and local; the default trace path
continues to discard natural-language bodies.

- [ ] Add an explicit content-analysis option to `CodexTraceReader` and emit
  user-message and agent-message events into the existing ordered trace stream.
- [ ] Retain only selected message text plus existing session, timestamp, agent
  lineage, role, event type, and source location; publish an inspection
  manifest listing every source field read.
- [ ] Extend `normalize_events()` to normalize message whitespace, volatile
  identifiers, timestamps, paths, and likely secrets, then attach a stable
  content fingerprint and deterministic token features.
- [ ] Preserve existing command, path, exit, error, mutation, and evidence
  signatures unchanged when content analysis is disabled.
- [ ] Keep raw message text in memory only for the opted-in analysis run;
  default JSON and Markdown output must remain body-free and use source
  locations, fingerprints, and explicitly requested review excerpts.
- [ ] Add privacy-safe fixtures covering user and agent messages, malformed
  content, redaction, stable fingerprints, inspection manifests, and the
  unchanged content-disabled path.

Completion criteria:

- Running without the content option produces byte-equivalent structured-trace
  events and reports.
- Every inspected content field is disclosed and linked to its source line.
- No message body is persisted to a report or sidecar without a separate,
  explicit review-output option.

### Product milestone 1c - Correlate messages with execution episodes (`v0.2.2`)

Use message content to explain structured activity: what request or plan led to
which reads, searches, failures, mutations, tests, and subagent work.

- [ ] Segment the unified timeline into reviewable work episodes using explicit
  user requests, agent hand-offs, idle gaps, repository/workdir changes, and
  terminal mutation or test evidence; expose every boundary rule.
- [ ] Implement a deterministic similarity ladder: exact normalized
  fingerprint, containment, identifier-aware token overlap, character n-grams,
  and local BM25/TF-IDF matching. Exclude greetings, acknowledgements, quoted
  tool output, and other low-information boilerplate.
- [ ] Correlate similar messages with normalized commands, paths, error
  fingerprints, tool sequences, mutations, tests, timestamps, and agent
  lineage from the same event stream.
- [ ] Add high-precision candidates for repeated investigation without
  progress, ineffective retry loops, and probable semantic subagent
  duplication. Require multiple independent signals and explicit exclusions.
- [ ] Extend the existing finding format and sidecar review flow with
  `evidence_kind` (`structured`, `content`, or `combined`), matching rule,
  shared anchors, boundary evidence, and confirm/reject/correct decisions.
- [ ] Add deterministic fixtures for exact and near matches, legitimate repeated
  work after mutation, generic-message suppression, changed task context, and
  missing-evidence outcomes.

Completion criteria:

- Similar wording alone never becomes a waste finding.
- Each combined candidate links message similarity to execution evidence and
  explains which progress signal was absent or present.
- Users can reject or correct every episode boundary and candidate without
  changing provider logs.

### Product milestone 1d - Expand and validate the waste-analysis catalog (`v0.2.3`)

Turn the integrated evidence model into a high-precision, explainable catalog.
This milestone validates insight quality; it does not create a composite waste
or model-quality score.

- [ ] Define stable rule IDs with required evidence, exclusions, derivation,
  confidence, unavailable conditions, and one narrowly scoped remediation.
- [ ] Add progress-aware rules for output that has no observed downstream use,
  repeated knowledge retrieval, test churn, failure-and-recovery episodes,
  cache/context churn, reopened resolved work, and duplicated exploration.
- [ ] Track transparent metrics separately: token exposure, output size,
  retries, repeated operations, elapsed time, cache changes, mutations, and
  test outcomes. Never assign fixed per-hit waste tokens or combine them into
  a grade.
- [ ] Add per-user and per-repository baselines for comparison while retaining
  the raw current value, baseline window, evidence availability, and sample
  size.
- [ ] Record user verdicts (`avoidable`, `intentional`, `inconclusive`, or
  `false_positive`) and use them to tune explicit local thresholds rather than
  training or calling an external model.
- [ ] Review at least twenty candidates across at least ten representative
  local tasks or sessions, including successful, partial, and failed work.
  Record whether each candidate informs a concrete prompting, context, tool,
  retry, delegation, or task-decomposition decision.

Completion criteria:

- At least one evidence-backed candidate changes or materially informs a real
  workflow decision; otherwise the catalog is revised or not promoted.
- Confirmed false positives and intentional repetitions are documented and
  reflected in rule exclusions or thresholds.
- Reports rank or filter findings only by transparent dimensions such as
  observed token exposure, recurrence, and confidence; never by a composite
  score.

### Product milestone 1e - Operationalize validated insights (`v0.2.4`)

Start only when milestone 1d produces meaningful, reviewable insight. If it
does not, archive the experimental analysis instead of shipping an unsupported
workflow. This milestone owns the residual P1A-5 work.

- [ ] Add an explicit experimental CLI command and input-path/content options
  while preserving all existing CLI behavior.
- [ ] Keep the workflow offline and prohibit external LLM or analytics calls.
- [ ] Generate deterministic JSON and Markdown containing structured, content,
  and combined findings, inspection manifests, evidence links, user reviews,
  and explicit unavailable labels.
- [ ] Document the evidence and content boundaries, privacy behavior, rule
  catalog, limitations, sidecar workflow, and the exact meaning of "first
  observed successful repository mutation".
- [ ] Validate installed console and module entry points on representative
  local sessions and publish no effectiveness claim beyond milestone 1d's
  reviewed evidence.

Completion criteria:

- The experimental CLI is opt-in, local, deterministic, and preserves the
  existing stable command behavior.
- A user can inspect, confirm, reject, and correct every reported finding.
- Documentation distinguishes observed activity, candidate waste, user verdict,
  and validated workflow insight.

### Product milestone 2 - Complete the reusable analysis boundary (`v0.3.0`)

Start this milestone only after milestone 1d demonstrates useful, reviewable
waste-analysis signal and milestone 1e operationalizes the validated local
workflow. The pilots should determine the
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

## Sprint-planning backlog

These are implementation-ready or preparatory work packages, not product
milestones. Pull them into a sprint only when they support the current roadmap
milestone and their listed dependencies are satisfied.

### Structural and parser improvements
#### L1 - Introduce typed usage records

- [ ] Add typed `UsageRecord`, `UsageSummary`, and diagnostic dataclasses.
- [ ] Change internal aggregation to use typed records.
- [ ] Provide dictionary conversion for existing callers.
- [ ] Test construction, conversion, equality, and parser output.

Dependencies: all high-priority parser work.

#### L2 - Split filesystem discovery from record parsing

- [ ] Extract the validated M2 discovery behavior into a shared layer for
  input validation and deterministic JSONL discovery.
- [ ] Keep provider-specific record interpretation inside each parser.
- [ ] Preserve current single-file and recursive-directory behavior.
- [ ] Test files, recursive directories, empty directories, invalid paths, and
  deterministic discovery order.

Dependencies: M2 and L1.

#### L3 - Separate aggregation from console rendering

- [ ] Make aggregation a pure operation over usage records.
- [ ] Build console output from `UsageSummary`.
- [ ] Preserve `parser.summary()` as a compatibility wrapper during the 0.x
  series.
- [ ] Test aggregation without stdout and add focused renderer assertions.

Dependencies: L1.

#### L4 - Rename the CLI module

- [ ] Move the CLI implementation from `burnrate/main.py` to
  `burnrate/cli.py`.
- [ ] Update package and console entry points.
- [ ] Retain `burnrate.main` as a compatibility re-export during the 0.x
  series.
- [ ] Test the old import, new import, console command, and module execution.

Dependencies: M3.

#### L5 - Strengthen the `BaseParser` contract

- [ ] Retain `BaseParser` and type its parsing, summary, diagnostics, and input
  status contract.
- [ ] Move common state-reset behavior into a protected helper only where the
  implementations are identical.
- [ ] Test that both concrete parsers satisfy the contract and reset all shared
  state.

Dependencies: L1 and L3.

#### L6 - Isolate parser tests

- [ ] Replace fixed repository-root mock directories with
  `TemporaryDirectory`.
- [ ] Ensure cleanup occurs even when a test fails.
- [ ] Preserve all existing behavioral coverage.

Dependencies: none.

#### L7 - Add linting and formatting checks

- [ ] Configure Ruff for Python 3.9.
- [ ] Apply formatting as a dedicated mechanical change.
- [ ] Document lint and formatting-check commands for contributors.

Dependencies: L6.

#### L8 - Add continuous integration

- [ ] Run unit tests on Python 3.9 and the latest stable Python available in
  GitHub Actions.
- [ ] Run Ruff checks and package-build smoke tests.
- [ ] Cache only safe dependency and build artifacts.

Dependencies: M4 and L7.

#### L9 - Complete package metadata

- [ ] Declare the MIT license, author, repository URL, issue tracker, and
  relevant package classifiers.
- [ ] Use the existing repository and license information.
- [ ] Validate the metadata through the built wheel.

Dependencies: M4.

#### L10 - Unify the API pricing structure

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

#### L11 - Estimate Codex credit-equivalent usage

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

#### L12 - Investigate a Claude retail-plan usage proxy

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

#### L13 - Extract small shared parser helpers

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

#### L14 - Add Claude cache-duration pricing

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

#### L15 - Add OpenAI long-context pricing

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

#### L16 - Add Claude conditional and long-context pricing

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
