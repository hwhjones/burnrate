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

From the repository root:

```powershell
python main.py
```

`main.py` imports `CodexParser` and `ClaudeParser` from the `parsers` package and currently runs `CodexParser` by default.

### Custom log file

If you want to use a different log file, update `parsers/codex_parser.py` to accept a path or modify `main.py` to pass a `log_path` to `CodexParser`.

## Testing

Run the existing test script directly:

```powershell
python tests/test_codex_parser.py
```

## Notes and recommendations

- `parsers/base.py` defines the parser interface.
- `parsers/codex_parser.py` is the main implementation for Rollout-style JSONL token count logs.
- `parsers/claude_parser.py` is currently a stub and requires a real Claude log parser implementation.
- `tests/test_codex_parser.py` should be refactored into a proper `pytest` test case with assertions and temporary file handling.

## Future improvements

- Add explicit CLI arguments for parser selection and log path
- Replace `print()` output with structured return values and logging
- Improve session handling and reset-aware delta calculation in `CodexParser`
- Add real `ClaudeParser` support
- Add a `requirements.txt` or `pyproject.toml` for dependency management
