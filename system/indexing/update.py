"""
Update pipeline: indexes new Zotero papers, then bridges papers.db into Obsidian notes.

- Uses a lock file so concurrent triggers don't overlap — only one run at a time.
- Skips the bridge step if indexing found nothing new (saves ~30 sec on idle runs).
- Uses normal (non-force) bridge — won't overwrite manually edited frontmatter.

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

# Must match the constants in index_papers_v2.py
EXIT_NEW_INDEXED = 0
EXIT_NOTHING_NEW = 10


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
    """Returns the subprocess return code, or None on launch failure."""
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
        return None

    for line in (result.stdout or "").strip().split("\n"):
        if line:
            log(f"  {line}")
    for line in (result.stderr or "").strip().split("\n"):
        if line:
            log(f"  STDERR: {line}")

    log(f"DONE: {label} (exit code {result.returncode})")
    return result.returncode


def main():
    if LOCK_FILE.exists():
        log("Already running -- skipping this trigger.")
        return

    try:
        LOCK_FILE.write_text(str(os.getpid()))
        log("=" * 60)
        log(f"Update run starting (dry_run={DRY_RUN})")

        index_code = run(INDEX_SCRIPT, "Indexing")

        if index_code is None or index_code not in (EXIT_NEW_INDEXED, EXIT_NOTHING_NEW):
            log(f"Indexing failed (exit code {index_code}); skipping bridge.")
            sys.exit(1)

        if index_code == EXIT_NOTHING_NEW:
            log("No new papers indexed — skipping bridge.")
            log("Update run complete.")
            log("")
            return

        # New papers were indexed: run bridge in normal (non-force) mode
        bridge_args = ["--dry-run"] if DRY_RUN else []
        bridge_code = run(BRIDGE_SCRIPT, "Bridging", extra_args=bridge_args)
        if bridge_code != 0:
            log("Bridge failed.")
            sys.exit(1)

        log("Update run complete.")
        log("")
    finally:
        LOCK_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()