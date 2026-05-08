"""
Targeted single-paper update.

Triggered when a paper note is created in Obsidian. Reads the note's frontmatter
to get the citekey, indexes that one paper if needed, then writes back to the note.

Self-filters to only process files in Notes/Papers/ — Shell Commands can fire
on every file creation; this script silently skips non-paper files.

Usage (from Shell Commands plugin):
    python update_one.py "{{event_file_path}}"
"""

import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import frontmatter

load_dotenv()
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / "papers.db"
LOG_FILE = SCRIPT_DIR / "update_one.log"


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    print(line, end="")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def main():
    if len(sys.argv) < 2:
        log("ERROR: no file path provided")
        sys.exit(1)

    note_path = Path(sys.argv[1])
    if not note_path.exists():
        log(f"File not found: {note_path}")
        sys.exit(1)

    # Only process files in Notes/Papers/ — silently skip everything else
    path_str = str(note_path)
    if "Notes\\Papers" not in path_str and "Notes/Papers" not in path_str:
        sys.exit(0)

    # Wait for Zotero Integration to finish writing
    time.sleep(3)

    # Read frontmatter
    try:
        post = frontmatter.load(note_path)
    except Exception as e:
        log(f"Couldn't read frontmatter: {e}")
        sys.exit(1)

    citekey = post.metadata.get("zotero_key")
    if not citekey:
        log(f"No zotero_key in frontmatter; not a Zotero-imported paper: {note_path.name}")
        sys.exit(0)

    log(f"Processing: {citekey}")

    # Check if already in DB
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT zotero_key FROM papers WHERE citekey = ? OR zotero_key = ?",
        (citekey, citekey)
    ).fetchone()

    if not row:
        log("Not in papers.db; indexing now...")
        conn.close()
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "index_papers_v2.py")],
            cwd=str(SCRIPT_DIR),
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            log(f"Indexing failed: {result.stderr[:500]}")
            sys.exit(1)
        log("Indexing complete")
        conn = sqlite3.connect(DB_PATH)
    else:
        log("Already in papers.db; skipping indexing")

    # Bridge just this one paper
    log("Bridging this paper...")
    paper = conn.execute(
        "SELECT * FROM papers WHERE citekey = ? OR zotero_key = ?",
        (citekey, citekey)
    ).fetchone()

    if not paper:
        log("Paper still not in DB after indexing — likely no PDF available")
        conn.close()
        sys.exit(0)

    cols = [d[0] for d in conn.execute("SELECT * FROM papers LIMIT 1").description]
    paper_dict = dict(zip(cols, paper))
    conn.close()

    field_map = {
        "title": "title",
        "authors": "authors",
        "year": "year",
        "venue": "venue",
        "doi": "doi",
        "summary": "summary",
        "methods": "methods",
        "datasets": "datasets",
        "key_claims": "key_claims",
        "limitations": "limitations",
        "tags": "tags",
        "themes": "themes",
    }

    updated = []
    for fm_key, db_col in field_map.items():
        if db_col not in paper_dict:
            continue
        value = paper_dict[db_col]
        if value is None:
            continue
        if db_col in ("authors", "methods", "datasets", "key_claims", "limitations", "tags", "themes"):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                if not isinstance(value, list):
                    value = []
        post.metadata[fm_key] = value
        updated.append(fm_key)

    post.metadata["last_updated"] = datetime.now().strftime("%Y-%m-%d")

    with open(note_path, "wb") as f:
        frontmatter.dump(post, f)

    log(f"Updated frontmatter fields: {', '.join(updated)}")
    log("Done.")


if __name__ == "__main__":
    main()