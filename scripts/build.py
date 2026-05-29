#!/usr/bin/env python3
"""Arena Buddy — build and package script.

Usage:
    python scripts/build.py              # Run tests
    python scripts/build.py package      # Create PyInstaller .exe (Windows)
    python scripts/build.py clean        # Remove build artifacts
    python scripts/build.py setup        # Install all deps + pyinstaller
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
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), **kwargs)
    except FileNotFoundError:
        print(f"  ✗ Command not found: {cmd[0]}")
        print(f"  Run 'python scripts/build.py setup' to install missing tools.")
        sys.exit(1)
    if result.returncode != 0:
        print(f"  ✗ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    print("  ✓")


def cmd_setup() -> None:
    """Install all dependencies including pyinstaller."""
    print("=== Installing dependencies ===")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"])
    run([sys.executable, "-m", "pip", "install", "-e", "."])
    run([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("\n  ✓ Setup complete.")


def cmd_test() -> None:
    """Run pytest with coverage."""
    print("=== Running Tests ===")
    run([sys.executable, "-m", "pytest", "tests/", "-q"])


def cmd_package() -> None:
    """Build Windows .exe with PyInstaller."""
    if sys.platform != "win32":
        print("  ⚠  PyInstaller packaging requires Windows. Skipping .exe build.")
        print("  Run this command on a Windows machine to create the binary.")
        return

    # Check pyinstaller is installed
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("  ✗ PyInstaller is not installed.")
        print("  Run: python scripts/build.py setup")
        sys.exit(1)

    print("=== Building ArenaBuddy.exe ===")
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "arena_buddy.spec",
    ])
    print(f"\n  ✓ Build complete → {ROOT / 'dist' / 'ArenaBuddy.exe'}")


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
        "setup": cmd_setup,
        "test": cmd_test,
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
