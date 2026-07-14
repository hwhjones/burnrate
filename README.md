# BurnRate

BurnRate is a small, dependency-free Python utility that parses Codex and Claude JSONL session logs, summarizes token usage, and estimates cost.

## Features

- Parse a single JSONL log file or recursively scan a directory.
- Support Codex rollout logs and Claude project logs.
- Report input, output, cached, and reasoning-token usage where available.
- Group usage and estimated cost by date and model.
- Estimate a 30-day cost from the observed calendar range.
- Report unknown models as unpriced instead of silently applying fallback rates.

## Requirements

- Python 3.9 or newer
- No third-party runtime dependencies

## Installation

Create a virtual environment and install BurnRate from the repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

Alternatively, install it directly from GitHub:

```powershell
python -m pip install git+https://github.com/hwhjones/burnrate.git
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

## Python usage

Parsers can also be used directly:

```python
from burnrate.parsers import CodexParser

parser = CodexParser("path/to/logs")
runs = parser.parse()
parser.summary()
```

`parse()` returns the parsed usage records and populates aggregate values on the parser instance.

## Cost estimates

BurnRate reports cost as API-equivalent USD using the static model tables bundled with the application. The source URL, units, verification date, and effective-date status for each provider are recorded in `burnrate/pricing.py`. These rates may need updating when providers change their prices or introduce new models.

These estimates are not provider invoices. BurnRate does not currently calculate Codex credit use.

Unknown models are still included in token totals, but they are displayed as `UNPRICED`. When unpriced models are present, cost totals and projections are marked as incomplete.

The projected 30-day cost is calculated from the average daily cost across the inclusive calendar range between the earliest and latest parsed records. A short observation period may produce a volatile projection.

## Testing

Run the complete test suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If the virtual environment is already activated:

```powershell
python -m unittest discover -s tests -v
```

## Project structure

```text
burnrate/
|-- burnrate/
|   |-- __main__.py
|   |-- main.py
|   |-- pricing.py
|   `-- parsers/
|       |-- base.py
|       |-- codex_parser.py
|       `-- claude_parser.py
|-- tests/
|   |-- test_codex_parser.py
|   `-- test_claude_parser.py
|-- pyproject.toml
`-- README.md
```

## License

BurnRate is available under the MIT License. See [LICENSE](LICENSE) for details.
