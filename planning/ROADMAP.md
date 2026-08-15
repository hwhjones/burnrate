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

Deliver the six-stage vertical slice in
[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

The release includes:

- three direct observations: repeated reads, ineffective retries, and test
  churn;
- ten frequency signals: exploration pile-up, long session, token pile-up,
  large output, subagent-heavy session, web-heavy session, context pressure,
  input-token growth, uncached input volume, and temporal output-to-input
  relationship;
- a concise frequency-ranked text report;
- deterministic JSON and optional source examples;
- one qualified experiment per displayed pattern;
- an opt-in Codex-only CLI path.

Success means users can run one command and understand the most frequent
patterns without learning an evidence schema.

The accepted `v0.2.0` baseline is 13 active rules (three direct observations
and ten frequency signals) implemented across four focused analyser modules.
The context module and its context/cache/carry signals are part of this
release, not deferred scope. Further rule or module growth requires a new
evidence-backed milestone decision.

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

### Deferred MVP - opt-in aggregate report relay

If a small cloud or edge deployment is useful for validating operational cloud
experience, build an opt-in relay around the existing local report rather than
moving detection into the cloud. BurnRate remains the source of truth: it reads
logs, applies rules, and constructs the report locally. The remote component
accepts only an explicitly allowlisted aggregate envelope.

**User outcome**

A user can publish a privacy-safe report snapshot, retrieve their recent
snapshots, and see direct period-to-period count changes. This is a deployment
and longitudinal-access experiment, not a hosted analysis product and not proof
that a workflow intervention caused a change.

**Smallest useful architecture**

```text
BurnRate CLI
  |  explicit `publish` of aggregate JSON over HTTPS with AWS IAM signing
  v
One Lambda Function URL
  |  route request, validate schema, reject unknown fields
  v
One DynamoDB on-demand table with TTL
  |
  +--> GET recent snapshots
  `--> GET direct count deltas
```

The default implementation uses one AWS Lambda function with a Function URL,
one DynamoDB table in on-demand capacity mode, short-retention CloudWatch logs,
and Terraform. It has no continuously running compute, provisioned database
capacity, API Gateway, load balancer, NAT gateway, custom domain, or other
resource with a standing application charge. Storage, requests, and function
execution are paid only when used, subject to AWS free allowances.

Use the Function URL's `AWS_IAM` authentication mode. The CLI signs requests
with the operator's existing AWS credentials, avoiding Cognito, a user store,
API-key infrastructure, and a paid secret-management service. One Lambda
function handles the complete method and path contract.

An alternative zero-cost-capped implementation can use a Cloudflare Worker and
D1 on their free plans. Treat this as an edge variant, not the default: moving
beyond its included limits may require a plan with a monthly minimum rather
than strict pay-per-use billing. Both variants should retain the same narrow
HTTP and data contracts.

**MVP scope**

- Add an explicit `burnrate publish` command; ordinary scans never contact a
  network service.
- Upload report schema version, an opaque installation ID, scan window, scan
  completion status, session/file counts, rule IDs, native counts, affected
  session counts, thresholds, and telemetry-coverage counts.
- Exclude log records, prompts, responses, reasoning, tool-output bodies,
  commands, paths, source references, repository names, model-generated text,
  and experiments containing free text.
- Validate an exact versioned request schema at the boundary and reject unknown
  fields, oversized payloads, unsupported versions, and invalid count ranges.
- Authenticate a single operator through AWS IAM and a least-privilege policy.
  Do not add API tokens, registration, social login, organisations, or role
  management.
- Store snapshots under an opaque owner key with a short configurable TTL,
  such as 30 days. Support deletion of all snapshots for that owner.
- Make uploads idempotent using a locally generated report ID or content hash.
- Expose only `POST /reports`, `GET /reports`, `GET /reports/{id}`, and
  `DELETE /reports`. Calculate deltas from matching rule IDs and preserve each
  rule's native unit rather than creating a score.
- Return unavailable or incompatible comparisons explicitly when schema,
  window, threshold, or telemetry coverage differs.

**Operational implementation**

- Define the Function URL, one Lambda function, one DynamoDB on-demand table,
  TTL policy, short log retention, cost alarm, and least-privilege permissions
  in Terraform.
- Deploy through a small CI pipeline with unit tests, schema-contract tests,
  an infrastructure validation step, and one disposable portfolio environment.
  Use CI workload identity where available instead of stored cloud keys.
- Record request IDs, latency, status, validation failures, throttling, and
  aggregate service errors without logging request bodies or credentials. Use
  standard Lambda metrics and short-retention structured logs; do not create a
  custom paid dashboard.
- Add payload limits, reserved-concurrency protection, encryption in transit
  and at rest, dependency scanning, and a disposable-data policy. Do not add a
  VPC or NAT gateway.
- Publish a small cost budget and alarm. The design must have no minimum monthly
  application-service commitment and no continuously running compute.

**Validation and acceptance**

- A fresh infrastructure deployment can be created and destroyed from the
  documented commands without manual console configuration.
- A local fixture can publish, retrieve, compare, and delete snapshots through
  the deployed endpoint.
- Contract tests prove that raw logs, paths, commands, source examples, and
  unexpected fields cannot be accepted or persisted.
- Repeating the same upload does not create a duplicate snapshot.
- Expired and explicitly deleted snapshots are no longer retrievable.
- Standard metrics, logs, and a cost alarm expose failed requests, throttling,
  latency, and unexpected spend without capturing report contents.
- A short architecture note records the threat model, privacy boundary,
  provider cost, deployment trade-offs, and evidence that local reporting still
  works with the network unavailable.

**Deliberately excluded from the MVP**

- raw-log upload or server-side pattern detection;
- a multi-user web application, teams, sharing, billing, or subscriptions;
- server-generated coaching, recommendations, rankings, or waste scores;
- cross-user benchmarks or training data;
- background upload, notifications, or automatic telemetry;
- indefinite retention or a generic event-ingestion platform;
- API Gateway, load balancers, containers, virtual machines, VPC networking,
  NAT gateways, custom domains, WAF, Cognito, or paid secret storage;
- separate permanent development and production environments, custom
  dashboards, cross-region replication, and point-in-time recovery.

This MVP is successful if it demonstrates a secure, observable, reproducible
cloud delivery path while preserving BurnRate's local-first product boundary.
It should remain deferred until the local report is validated or until the
deployment itself is the explicit learning objective.

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
