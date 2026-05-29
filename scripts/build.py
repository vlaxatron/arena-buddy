#!/usr/bin/env python3
"""Arena Buddy — build and package script.

Usage:
    python scripts/build.py              # Run tests + lint
    python scripts/build.py package      # Create PyInstaller .exe (Windows)
    python scripts/build.py clean        # Remove build artifacts
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], **kwargs) -> None:
    """Run a command, exiting on failure."""
    print(f"\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT), **kwargs)
    if result.returncode != 0:
        print(f"  ✗ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print("  ✓")


def cmd_test() -> None:
    """Run pytest with coverage."""
    print("=== Running Tests ===")
    run(["python", "-m", "pytest", "tests/", "-q", "--cov=arena_buddy", "--cov-report=term-missing"])


def cmd_lint() -> None:
    """Run ruff linter (if installed)."""
    try:
        import ruff  # noqa: F401
    except ImportError:
        print("=== Lint skipped (ruff not installed) ===")
        return

    print("=== Running Linter ===")
    run(["python", "-m", "ruff", "check", "src/", "tests/"])


def cmd_package() -> None:
    """Build Windows .exe with PyInstaller."""
    if sys.platform != "win32":
        print("  ⚠ PyInstaller packaging requires Windows. Skipping .exe build.")
        print("  Run this command on a Windows machine to create the binary.")
        return

    print("=== Building ArenaBuddy.exe ===")
    run([
        "pyinstaller",
        "--clean",
        "--noconfirm",
        "arena_buddy.spec",
    ])
    print("\n  ✓ Build complete → dist/ArenaBuddy.exe")


def cmd_clean() -> None:
    """Remove build artifacts."""
    dirs_to_clean = ["build", "dist", "__pycache__", ".pytest_cache"]
    patterns = ["*.spec.bak", "*.pyc"]

    for d in dirs_to_clean:
        path = ROOT / d
        if path.exists():
            shutil.rmtree(path)
            print(f"  Removed {d}/")

    for pattern in patterns:
        for f in ROOT.rglob(pattern):
            f.unlink()
            print(f"  Removed {f}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"

    commands = {
        "test": cmd_test,
        "lint": cmd_lint,
        "package": cmd_package,
        "clean": cmd_clean,
    }

    if cmd not in commands:
        print(f"Usage: python scripts/build.py [{'|'.join(commands)}]")
        sys.exit(1)

    commands[cmd]()
    print("\nDone.")


if __name__ == "__main__":
    main()
