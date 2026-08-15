# BurnRate 0.2.0

BurnRate is a small, dependency-free Python utility that parses Codex and Claude JSONL session logs, summarizes token usage, and estimates cost.

Version 0.2 adds an opt-in, local-only Codex workflow scan while preserving the
existing usage and cost accounting. It reads session metadata, ranks bounded
workflow signals, and suggests one experiment to try next. It does not upload
logs, retain prompt bodies, or claim to measure waste, correctness, or
verification success.

## Features

- Parse a single JSONL log file or recursively scan a directory.
- Support Codex rollout logs and Claude project logs.
- Report input, output, cached, and reasoning-token usage where available.
- Group usage and estimated cost by date and model.
- Estimate a 30-day cost from the observed calendar range.
- Report unsupported pricing conditions as unpriced instead of guessing.
- Read ordinary and BOM-prefixed UTF-8 JSONL files.

## What's new in 0.2.0

- Hardened token, identity, session-deduplication, and malformed-record handling.
- Added resilient filesystem diagnostics and meaningful CLI exit statuses.
- Refreshed OpenAI Codex and Anthropic Claude API-equivalent USD rates and
  made unpriced or partial estimates visible.
- Added the `patterns` command for a concise ranked report from local Codex logs.
- Added `--explain` for thresholds, telemetry coverage, bounded examples, and
  source references; `--json` exposes the complete machine-readable result.
- Keeps missing telemetry from becoming a finding and keeps every displayed
  number a direct count or session-local aggregate.
- Refreshed current OpenAI and Anthropic API-equivalent pricing tables,
  including a clearly starred qualified estimate for `codex-auto-review`.
- Bumped package metadata and release documentation to `0.2.0`.

Known limitation: conditional pricing variants and Codex subscription credits are
not calculated; estimates use the documented standard API-rate assumptions below.

## Requirements

- Python 3.9 or newer
- No third-party runtime dependencies

## Installation

Create a virtual environment and install BurnRate from the repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
```

For an end-user installation, install the published release instead of
cloning the repository:

```powershell
python -m pip install token-burnrate==0.2.0
```

If the release is being distributed before it is on PyPI, give users the wheel
from the release artifacts and install it directly:

```powershell
python -m pip install token_burnrate-0.2.0-py3-none-any.whl
```

The wheel and source archive are created with:

```powershell
python -m build --sdist --wheel
```

For maintainers, the repository includes a GitHub Actions release workflow.
Configure the `hwhjones/burnrate` repository as a PyPI Trusted Publisher for
the `token-burnrate` project and `pypi` environment, then push a version tag
such as `v0.2.0`. GitHub will run the
tests, build both artifacts, and publish them without a stored PyPI password or
API token. PyPI's Trusted Publishing uses short-lived OIDC credentials for this
workflow.

BurnRate requires Python 3.9 or newer and has no third-party runtime
dependencies. After installation, the `burnrate` command is available on the
user's `PATH`.

## Usage

After installation, run BurnRate as a command-line tool:

```powershell
burnrate --parser codex
burnrate --parser claude
```

Run the opt-in Codex workflow pattern report with the preferred subcommand:

```powershell
python -m burnrate patterns
python -m burnrate patterns --days 20
python -m burnrate patterns --days 20 --explain
python -m burnrate patterns --days 20 --json
```

The `burnrate` executable is available after installing this checkout into the
active environment:

```powershell
python -m pip install -e .
burnrate patterns --days 20
```

The default report is intentionally short: it shows up to three ranked,
actionable signals and a runnable seven-day follow-up command. Use `--explain`
when reviewing a finding or validating a rule; it shows the threshold, native
counts, affected sessions, telemetry requirements, and bounded evidence. Use
`--json` for automation or to inspect all ranked signals.

If PowerShell still reports that `burnrate` is not recognized, use
`python -m burnrate ...`; it does not depend on the Scripts directory being on
`PATH`.

The report is designed to produce one workflow experiment worth trying, then a
seven-day command for checking the next scan. It reports observations and
frequency signals; it does not measure waste, code correctness, or successful
verification. The compatibility form `burnrate --patterns` accepts the same
pattern options.

For a reproducible twenty-day local smoke test against Codex logs:

```powershell
python -m burnrate patterns --parser codex --days 20 --log-path "$HOME/.codex/sessions"
```

Use `--explain` when you need thresholds, telemetry coverage, model/stream
scope, and source references. JSON is complete and is not capped to the three
patterns shown in the default text.

It can also be run as a Python module:

```powershell
python -m burnrate --parser codex
python -m burnrate --parser claude
```

The default log directories are:

- Codex: `~/.codex/sessions/`
- Claude: `~/.claude/projects/`

Use `--log-path` to analyze a specific JSONL file or directory:

```powershell
burnrate --parser codex --log-path C:\path\to\codex\logs
burnrate --parser claude --log-path C:\path\to\claude\logs
```

Display all command-line options with:

```powershell
burnrate --help
```

Exit status is `0` for a complete readable scan, including scans containing
reported malformed records; `1` for a partial scan caused by file-read or
directory-discovery errors; and `2` for an invalid top-level input path.

## Python usage

Parsers can also be used directly:

```python
from burnrate.parsers import CodexParser

parser = CodexParser("path/to/logs")
runs = parser.parse()
parser.summary()
```

`parse()` returns the parsed usage records and populates aggregate values on the parser instance.

Malformed and unusable records are counted by category. Rejected usage-like
records mark token totals as potentially incomplete. Unreadable files and
directory-discovery errors are reported by path; successfully parsed files are
retained and the scan is marked incomplete.

## Cost estimates

BurnRate reports API-equivalent USD using static model tables bundled with the
application. Pricing provenance is recorded in `burnrate/pricing.py`; the
tables were verified against the current OpenAI API pricing page and Anthropic
Claude pricing documentation on 2026-08-16. Estimates are not provider
invoices, and BurnRate does not calculate Codex credit use.

The tables assume standard first-party API rates. They include current Codex
models such as GPT-5.6, GPT-5.3-Codex, and Daybreak aliases, and current Claude
models including Opus 5/4.8/4.7/4.6/4.5, Sonnet 5/4.6/4.5, Haiku 4.5, and the
current Fable/Mythos 5 entries. Legacy model IDs remain available for
historical log analysis. Claude cache creation uses the 5-minute cache-write
rate because logs do not identify cache duration. Cache-duration, long-context,
regional, batch, fast-mode, and other conditional variants are not inferred
from logs.

Codex `codex-auto-review` records are priced using the GPT-5.4 standard API
rate as a qualified API-equivalent estimate. Auto-review is a subscription
approval/reviewer feature rather than a published API SKU, and its logs do not
expose the underlying billable model or a separate dollar rate; this estimate
must not be read as an invoice amount.

CLI rows and totals containing that estimate are marked with `*`, with a
legend printed below the Codex summary. Treat starred values as directional
estimates, not provider invoices.

Unknown models and records requiring a token-category rate that is not bundled
are retained in token totals but shown as `UNPRICED`. Reported cost is then the
known partial cost, and cost totals and projections are marked incomplete.

The 30-day projection uses dated known cost across the inclusive observed
calendar range. Undated records remain in totals but are reported and excluded
from projection; without a valid date, projection is unavailable.

## Testing

Run the complete test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Project structure

```text
burnrate/
|-- burnrate/
|   |-- __init__.py
|   |-- __main__.py
|   |-- main.py
|   |-- pricing.py
|   `-- parsers/
|       |-- __init__.py
|       |-- base.py
|       |-- codex_parser.py
|       `-- claude_parser.py
|-- scripts/
|   `-- smoke_build.py
|-- tests/
|   |-- __init__.py
|   |-- test_claude_parser.py
|   |-- test_cli.py
|   |-- test_codex_parser.py
|   |-- test_file_read_errors.py
|   |-- test_parser_diagnostics.py
|   |-- test_parser_validation.py
|   |-- test_pricing.py
|   |-- test_undated_projections.py
|   `-- test_version.py
|-- LICENSE
|-- pyproject.toml
`-- README.md
```

## License

BurnRate is available under the MIT License. See [LICENSE](LICENSE) for details.
