"""Build, install, and exercise BurnRate distribution artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, cwd: Path, expected_status: int = 0) -> None:
    """Run a command and require its expected process status."""
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != expected_status:
        raise RuntimeError(
            f"expected status {expected_status}, got {completed.returncode}: {command}"
        )


def environment_python(environment: Path) -> Path:
    """Return the Python executable created by venv on this platform."""
    directory = "Scripts" if os.name == "nt" else "bin"
    executable = "python.exe" if os.name == "nt" else "python"
    return environment / directory / executable


def console_script(environment: Path) -> Path:
    """Return the installed BurnRate console-script path."""
    directory = environment / ("Scripts" if os.name == "nt" else "bin")
    executable = "burnrate.exe" if os.name == "nt" else "burnrate"
    return directory / executable


def only_artifact(directory: Path, pattern: str) -> Path:
    """Require exactly one matching build artifact and return it."""
    artifacts = list(directory.glob(pattern))
    if len(artifacts) != 1:
        raise RuntimeError(
            f"expected one {pattern} artifact, found {len(artifacts)} in {directory}"
        )
    return artifacts[0]


def main() -> int:
    """Build an sdist and wheel, install the wheel, and smoke-test both CLIs."""
    with tempfile.TemporaryDirectory(prefix="burnrate-build-smoke-") as temporary:
        root = Path(temporary)
        artifacts = root / "dist"
        installed = root / "installed"
        outside_source = root / "run"
        outside_source.mkdir()

        run(
            [
                sys.executable,
                "-m",
                "build",
                "--sdist",
                "--wheel",
                "--outdir",
                str(artifacts),
                str(PROJECT_ROOT),
            ],
            cwd=outside_source,
        )
        source_distribution = only_artifact(artifacts, "*.tar.gz")
        wheel = only_artifact(artifacts, "*.whl")
        print(f"Built {source_distribution.name} and {wheel.name}")

        venv.EnvBuilder(with_pip=True).create(installed)
        python = environment_python(installed)
        run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheel)],
            cwd=outside_source,
        )
        run([str(console_script(installed)), "--help"], cwd=outside_source)
        run([str(python), "-m", "burnrate", "--help"], cwd=outside_source)
        missing = outside_source / "missing"
        run(
            [str(console_script(installed)), "--log-path", str(missing)],
            cwd=outside_source,
            expected_status=2,
        )
        run(
            [str(python), "-m", "burnrate", "--log-path", str(missing)],
            cwd=outside_source,
            expected_status=2,
        )

    print("Build smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
