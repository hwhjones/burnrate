# BurnRate

BurnRate is a small Python utility for parsing LLM usage logs and estimating token usage and cost.

## Project structure

- `main.py` — top-level entrypoint for running the analysis
- `parsers/` — parser package containing log parser implementations
  - `base.py` — parser interface definition
  - `codex_parser.py` — example parser for `rollout-*.jsonl` usage logs
  - `claude_parser.py` — placeholder parser for Claude logs
- `tests/` — parser test coverage
  - `test_codex_parser.py`

## Requirements

- Python 3.7+
- No external dependencies (uses standard library only)

## Installation

Install BurnRate as a package:

```bash
# From the repository directory
pip install -e .

# Or install from GitHub directly (once published)
pip install git+https://github.com/yourusername/burnrate.git
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
```

> There is no dependency file currently defined, so the project only requires the standard library.

## Usage

### Traditional Usage (Legacy Support)

From the repository root, run the main entrypoint:

```powershell
python main.py
```

This will run the default parser (`codex`) against the default log path configured in `main.py`.

By default, `python main.py` uses:

- parser: `codex`
- log path: `~/.codex/sessions/`

#### Run with explicit parser selection

Use the `--parser` flag to choose between the built-in parsers.

```powershell
python main.py --parser codex
python main.py --parser claude
```

#### Run with a custom log path

Use the `--log-path` flag to analyze a specific file or directory:

```powershell
python main.py --parser codex --log-path C:\path\to\logs
python main.py --parser claude --log-path C:\path\to\claude\sessions\
```

The parser class and log path are selected from `PARSER_MAP` in `main.py`, so this is the preferred way to run the tool.

### Modern Package Usage (Recommended)

After installation, you can use BurnRate in multiple ways:

#### As a Command Line Tool
```bash
# Global command - works from any directory
burnrate --parser codex
burnrate --parser claude
burnrate --parser codex --log-path /custom/path/to/logs

# Get help
burnrate --help
```

#### As a Python Module
```bash
# Module execution - works from any directory
python -m burnrate --parser codex
python -m burnrate --parser claude --log-path /path/to/logs
```

#### As an Importable Package
```python
import burnrate

# The existing run() function can be called programmatically
# (Note: for programmatic usage, you'll need to handle arguments manually)
```

## Testing

Run the existing test script directly:

```powershell
python tests/test_codex_parser.py
```

## Notes and recommendations

- `parsers/base.py` defines the parser interface.
- `parsers/codex_parser.py` is the main implementation for Rollout-style JSONL token count logs.
- `parsers/claude_parser.py` now includes a robust implementation for Claude logs. It uses a buffered aggregation strategy to correctly de-duplicate cumulative usage reports.
- `tests/test_codex_parser.py` and `tests/test_claude_parser.py` are now structured as `unittest.TestCase` classes with basic parsing and summary output assertions.
- Both parsers implement a "Collection Pass" and "Aggregation Pass" to handle cumulative usage reporting in logs, ensuring accurate de-duplication by request ID.

## Future improvements

- Replace `print()` output with structured return values and logging
- Add a `requirements.txt` or `pyproject.toml` for dependency management
