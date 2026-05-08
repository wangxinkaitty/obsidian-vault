"""
Update pipeline: indexes new Zotero papers, then bridges papers.db into Obsidian notes.

Uses a lock file so concurrent triggers don't overlap — only one run at a time.

Usage:
    python update.py            # Run normally
    python update.py --dry-run  # Preview only (bridge runs in dry-run mode)
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = SCRIPT_DIR / "update.log"
LOCK_FILE = SCRIPT_DIR / "update.lock"
PYTHON = sys.executable
INDEX_SCRIPT = SCRIPT_DIR / "index_papers_v2.py"
BRIDGE_SCRIPT = SCRIPT_DIR / "bridge_papers.py"
DRY_RUN = "--dry-run" in sys.argv


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    print(line, end="")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def run(script_path, label, extra_args=None):
    log(f"=== {label} ===")
    cmd = [PYTHON, str(script_path)]
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SCRIPT_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as e:
        log(f"ERROR running {label}: {e}")
        return False

    for line in (result.stdout or "").strip().split("\n"):
        if line:
            log(f"  {line}")
    for line in (result.stderr or "").strip().split("\n"):
        if line:
            log(f"  STDERR: {line}")

    if result.returncode != 0:
        log(f"FAILED: {label} (exit code {result.returncode})")
        return False

    log(f"DONE: {label}")
    return True


def main():
    if LOCK_FILE.exists():
        log("Already running — skipping this trigger.")
        return

    try:
        LOCK_FILE.write_text(str(os.getpid()))
        log("=" * 60)
        log(f"Update run starting (dry_run={DRY_RUN})")

        if not run(INDEX_SCRIPT, "Indexing"):
            log("Indexing failed; skipping bridge.")
            sys.exit(1)

        bridge_args = ["--dry-run"] if DRY_RUN else ["--force"]
        if not run(BRIDGE_SCRIPT, "Bridging", extra_args=bridge_args):
            log("Bridge failed.")
            sys.exit(1)

        log("Update run complete.")
        log("")
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()