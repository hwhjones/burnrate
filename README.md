# BurnRate

BurnRate is a small, dependency-free Python utility that parses Codex and Claude JSONL session logs, summarizes token usage, and estimates cost.

## Features

- Parse a single JSONL log file or recursively scan a directory.
- Support Codex rollout logs and Claude project logs.
- Report input, output, cached, and reasoning-token usage where available.
- Group usage and estimated cost by date and model.
- Estimate a 30-day cost from the observed calendar range.
- Report unsupported pricing conditions as unpriced instead of guessing.
- Read ordinary and BOM-prefixed UTF-8 JSONL files.

## What's new in 0.1.1

- Hardened token, identity, session-deduplication, and malformed-record handling.
- Added resilient filesystem diagnostics and meaningful CLI exit statuses.
- Verified API-equivalent USD rates and made unpriced or partial estimates visible.
- Corrected build metadata and unified runtime and distribution version reporting.

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

## Usage

After installation, run BurnRate as a command-line tool:

```powershell
burnrate --parser codex
burnrate --parser claude
```

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
application. Pricing provenance is recorded in `burnrate/pricing.py`. Estimates
are not provider invoices, and BurnRate does not calculate Codex credit use.

The tables assume their standard published API rates. Claude cache creation uses
the single bundled cache-write rate. Cache-duration, long-context, geography,
batch, and other conditional variants are not inferred from logs.

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
