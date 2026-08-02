# BurnRate Product Roadmap

## Product direction

BurnRate is a local, dependency-free CLI for understanding coding-agent token
usage and cost. Its next job is to make recurring workflow patterns visible in
plain language without pretending to measure intent, quality, or avoidable
waste.

The product should remain:

- local and offline-first;
- useful without inspecting message bodies;
- deterministic and explainable;
- concise by default, with evidence available on request;
- free of composite scores and unsupported savings claims.

## Current baseline

`v0.1.1` provides hardened Codex and Claude usage parsing, token accounting,
API-equivalent cost estimates, pricing provenance, filesystem diagnostics,
packaging, and stable CLI exit behavior.

The structured-trace pilot was archived on
`agent/p1a-structured-trace-pilot`. It demonstrated that message correlation,
episode correction, review sidecars, baselines, and multi-stage candidate
schemas were too complex for the immediate product goal. Those components are
not part of the active implementation path.

## Deferred maintenance backlog

The following low-priority parser and packaging improvements were carried
forward from the v0.1.x plan. They were deferred, not cancelled. They should
be scheduled only when they improve maintainability or correctness without
complicating the workflow-pattern scanner.

| ID | Deferred fix | Dependency / note |
| --- | --- | --- |
| L1 | Introduce typed usage and summary records with dictionary compatibility | Existing parser contracts must remain stable |
| L2 | Split filesystem discovery from provider-specific record parsing | Depends on L1 and existing discovery hardening |
| L3 | Separate pure aggregation from console rendering | Depends on L1 |
| L4 | Rename the CLI module while retaining a compatibility import | Depends on existing CLI status work |
| L5 | Strengthen and type the `BaseParser` contract | Coordinate with L1 and L3 |
| L6 | Isolate parser tests with temporary directories and guaranteed cleanup | Independent maintenance |
| L7 | Add Ruff linting and formatting checks | Depends on L6 |
| L8 | Add CI for supported Python versions, lint, and package smoke tests | Depends on L7 and packaging work |
| L9 | Complete package metadata and validate the built wheel | Depends on packaging work |
| L10 | Unify provider API pricing under one explicit mapping | Depends on conditional pricing decisions |
| L11 | Estimate Codex credit-equivalent usage separately from API USD | Requires authoritative rates and clear limitations |
| L12 | Investigate a Claude retail-plan usage proxy without inventing allowance math | Keep unavailable unless provider data supports it |
| L13 | Extract small shared parser helpers without creating a parser framework | Coordinate with L1-L5 |
| L14 | Add Claude cache-duration pricing when duration breakdowns are reliable | Requires provider-published rates |
| L15 | Add OpenAI long-context pricing with explicit thresholds | Requires authoritative model thresholds |
| L16 | Add Claude conditional and long-context pricing | Requires reliable condition metadata and rates |

These items are maintenance or accounting work, not prerequisites for the
workflow-pattern scan. The active implementation plan remains deliberately
small; a future PR may promote one of these items when there is a concrete
failure, maintenance cost, or accounting requirement.

## Planned releases

| Milestone | Version | Outcome |
| --- | --- | --- |
| 1 | `v0.2.0` | Ship the Codex workflow pattern scan |
| 2 | `v0.2.1` | Validate usefulness and tune transparent thresholds |
| 3 | `v0.3.0` | Extend only the patterns and providers proven useful |
| Later | unassigned | Rich exports, pricing updates, and optional local analysis |

## Milestone 1 - Codex workflow pattern scan (`v0.2.0`)

Deliver the five-PR vertical slice in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

The release includes:

- three direct observations: repeated reads, ineffective retries, and test
  churn;
- six frequency signals: exploration pile-up, long session, token pile-up,
  large output, subagent-heavy session, and web-heavy session;
- a concise frequency-ranked text report;
- deterministic JSON and optional source examples;
- one qualified experiment per displayed pattern;
- an opt-in Codex-only CLI path.

Success means users can run one command and understand the most frequent
patterns without learning an evidence schema.

## Milestone 2 - Validate usefulness (`v0.2.1`)

Use synthetic fixtures for correctness and representative local logs only for
product validation.

- Review whether the ranked results change a concrete tool, context, retry,
  delegation, or task-decomposition decision.
- Record false positives and intentional repetitions as plain rule notes.
- Adjust named thresholds only when examples show a clear problem.
- Remove patterns that remain noisy or unactionable.
- Add recurrence-across-sessions language only if it improves comprehension.
- Keep observations, frequency signals, and any future habit candidates
  distinct.

This milestone does not introduce review infrastructure, persisted verdicts,
baselines, or a score.

## Milestone 3 - Proven extensions (`v0.3.0`)

Start only after the Codex scan is demonstrably useful.

Possible work, selected by evidence rather than completeness:

- support Claude logs through the same small result contract;
- add one or two high-value patterns that use already available telemetry;
- add CSV or richer JSON exports for personal analysis;
- improve project/session grouping where source metadata is reliable;
- distinguish recurring cross-session patterns from one-off occurrences;
- expose user-configurable thresholds without creating a rule engine.

Do not add all of these automatically. Each extension must improve the default
report or a demonstrated user workflow.

## Later possibilities

These remain uncommitted until the core scanner proves durable value:

- signed or checksummed pricing-card updates;
- historical rate-card selection;
- local HTML reports;
- optional content-aware analysis performed locally;
- local longitudinal summaries;
- additional coding-agent providers;
- user-defined token or cost budgets;
- subscription or credit-equivalent estimates when authoritative inputs exist.

## Explicitly deferred architecture

- natural-language similarity and semantic matching;
- inferred task episodes and boundary correction;
- candidate review sidecars and verdict training;
- personal or repository baselines;
- composite confidence systems;
- generic event, detector, or provider plugin frameworks;
- hosted services, accounts, telemetry, or cloud storage;
- waste scores, grades, percentages, or fixed per-hit token estimates.

Deferred does not mean forbidden forever. It means a concrete user need must
justify reintroducing the complexity.

## Product decision gates

Before expanding a milestone, answer:

1. Does this change make the default report more useful or more accurate?
2. Can its result be explained with direct local evidence?
3. Can it fit the existing result and aggregation path?
4. Is missing evidence handled by omission rather than speculation?
5. Is the implementation smaller than the user problem it solves?

If the answer to any question is no, defer the change.

## Long-term success criteria

- Users can identify recurring workflow patterns responsible for substantial
  activity.
- Every number is reproducible from local logs.
- Every suggested experiment is visibly qualified.
- Default scans remain private, offline, and body-free.
- Usage and cost accounting remain trustworthy as pattern analysis evolves.
- BurnRate stays understandable as a small utility rather than becoming an
  evidence-management platform.
