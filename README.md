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

- Python 3.11+ (project has been developed against Python 3.14)
- A virtual environment is recommended

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
```

> There is no dependency file currently defined, so the project only requires the standard library.

## Usage

From the repository root, run the main entrypoint:

```powershell
python main.py
```

This will run the default parser (`codex`) against the default log path configured in `main.py`.

By default, `python main.py` uses:

- parser: `codex`
- log path: `~/.codex/sessions/`

### Run with explicit parser selection

Use the `--parser` flag to choose between the built-in parsers.

```powershell
python main.py --parser codex
python main.py --parser claude
```

### Run with a custom log path

Use the `--log-path` flag to analyze a specific file or directory:

```powershell
python main.py --parser codex --log-path C:\path\to\logs
python main.py --parser claude --log-path C:\path\to\claude\sessions\
```

The parser class and log path are selected from `PARSER_MAP` in `main.py`, so this is the preferred way to run the tool.

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

- Add explicit CLI arguments for parser selection and log path
- Replace `print()` output with structured return values and logging
- Improve session handling and reset-aware delta calculation in `CodexParser`
- Add real `ClaudeParser` support
- Add a `requirements.txt` or `pyproject.toml` for dependency management
