#!/usr/bin/env python3
"""Create an isolated Python environment for SageMaker work. Cross-platform.

Idempotent. Prefers uv, falls back to the stdlib venv module.

Handles the platform difference in venv layout: the interpreter lives at
`<venv>/bin/python` on macOS/Linux and `<venv>\\Scripts\\python.exe` on Windows.
The path it prints is the correct one for the host OS.

Usage:
    python setup_env.py [VENV_DIR=.venv] [PYTHON_VERSION=3.12]
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# 3.10-3.12 is the safe zone for modern boto3 + awscli. 3.13+ may work but ML
# libs lag on wheel availability.
SUPPORTED_MIN = (3, 10)
SUPPORTED_MAX = (3, 12)

IS_WINDOWS = os.name == "nt"


def log(msg: str) -> None:
    print(f"[setup_env] {msg}", file=sys.stderr, flush=True)


def parse_version(v: str) -> tuple[int, int]:
    try:
        major, minor = (int(p) for p in v.split(".")[:2])
        return (major, minor)
    except ValueError:
        log(f"ERROR: invalid Python version '{v}' (expected e.g. 3.12)")
        sys.exit(1)


def venv_python(venv_dir: Path) -> Path:
    """Path to the interpreter inside a venv, per platform."""
    if IS_WINDOWS:
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def interpreter_version(python_path: Path) -> str | None:
    if not python_path.exists():
        return None
    proc = subprocess.run(
        [str(python_path), "-c",
         "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


def find_base_python(version: str) -> str | None:
    """Locate a base interpreter for the requested version for `python -m venv`."""
    # Try `pythonX.Y` (Unix) / `pythonX.Y.exe`, then the Windows `py` launcher.
    candidate = shutil.which(f"python{version}")
    if candidate:
        return candidate
    if IS_WINDOWS and shutil.which("py"):
        probe = subprocess.run(["py", f"-{version}", "--version"], capture_output=True, text=True)
        if probe.returncode == 0:
            return f"py -{version}"  # sentinel; expanded by caller
    return None


def main() -> int:
    venv_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".venv")
    python_version = sys.argv[2] if len(sys.argv) > 2 else "3.12"

    ver = parse_version(python_version)
    if not (SUPPORTED_MIN <= ver <= SUPPORTED_MAX):
        lo = ".".join(map(str, SUPPORTED_MIN))
        hi = ".".join(map(str, SUPPORTED_MAX))
        log(f"ERROR: Python {python_version} outside supported range {lo}-{hi}")
        log("Use 3.10, 3.11, or 3.12.")
        return 1

    installer = "uv" if shutil.which("uv") else "venv"
    if installer == "venv":
        log("uv not found — falling back to python + venv. Consider: https://docs.astral.sh/uv/")

    py = venv_python(venv_dir)

    # Reuse existing env only if Python version matches.
    current = interpreter_version(py)
    if current == python_version:
        log(f"Env exists at {venv_dir} with Python {current} — reusing")
    else:
        if current is not None:
            log(f"Env at {venv_dir} uses Python {current} (wanted {python_version}) — recreating")
            shutil.rmtree(venv_dir)

        if installer == "uv":
            uv = shutil.which("uv")
            if subprocess.run([uv, "venv", "--python", python_version, str(venv_dir)]).returncode != 0:
                log("ERROR: `uv venv` failed.")
                return 1
        else:
            base = find_base_python(python_version)
            if not base:
                log(f"ERROR: python{python_version} not found on PATH.")
                log("Install via pyenv/asdf/brew/system package manager, the Windows installer, or install uv.")
                return 1
            base_cmd = base.split() if base.startswith("py ") else [base]
            if subprocess.run([*base_cmd, "-m", "venv", str(venv_dir)]).returncode != 0:
                log("ERROR: `python -m venv` failed.")
                return 1
        log(f"Created env at {venv_dir}")

    requirements = Path(__file__).resolve().parent.parent / "requirements.txt"
    if not requirements.is_file():
        log(f"ERROR: requirements.txt not found at {requirements}")
        return 1

    log(f"Installing from {requirements}")
    if installer == "uv":
        uv = shutil.which("uv")
        rc = subprocess.run(
            [uv, "pip", "install", "--python", str(py), "--upgrade", "-r", str(requirements)]
        ).returncode
    else:
        subprocess.run([str(py), "-m", "pip", "install", "--upgrade", "pip"])
        rc = subprocess.run(
            [str(py), "-m", "pip", "install", "--upgrade", "-r", str(requirements)]
        ).returncode
    if rc != 0:
        log("ERROR: dependency install failed.")
        return 1

    log(f"Done. Invoke directly: {py} <script>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
