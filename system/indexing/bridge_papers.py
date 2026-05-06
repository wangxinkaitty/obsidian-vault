"""
Bridge papers.db → Obsidian paper-note frontmatter.

Reads structured metadata from papers.db and fills empty fields in
matching Obsidian paper notes. Preserves manual edits by default.

Match key: citekey, stored as `zotero_key` in Obsidian frontmatter.

Usage:
    python bridge_papers.py              # Apply updates
    python bridge_papers.py --dry-run    # Preview changes without writing
    python bridge_papers.py --force      # Overwrite non-empty fields too

Requires:
    pip install python-frontmatter
"""

import sys
import json
import sqlite3
from pathlib import Path

import frontmatter

# ─── Config ─────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPT_DIR.parent.parent  # D:\Vault\system\indexing → D:\Vault
PAPERS_DIR = VAULT_ROOT / "Notes" / "Papers"
DB_PATH = SCRIPT_DIR / "papers.db"

DRY_RUN = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv

FIELDS = ["methods", "datasets", "key_claims", "limitations", "tags"]


# ─── Load papers.db ─────────────────────────────────────────────────
def load_papers():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("""
        SELECT citekey, methods, datasets, key_claims, limitations, tags
        FROM papers
        WHERE citekey != ''
    """).fetchall()
    conn.close()

    papers = {}
    for citekey, methods, datasets, claims, limits, tags in rows:
        papers[citekey.strip()] = {
            "methods": json.loads(methods),
            "datasets": json.loads(datasets),
            "key_claims": json.loads(claims),
            "limitations": json.loads(limits),
            "tags": json.loads(tags),
        }
    return papers


# ─── Main ───────────────────────────────────────────────────────────
def main():
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} doesn't exist. Run index_papers.py first.")
        return

    papers = load_papers()
    print(f"Loaded {len(papers)} papers from {DB_PATH}")

    if not PAPERS_DIR.exists():
        print(f"ERROR: {PAPERS_DIR} doesn't exist")
        return

    note_files = list(PAPERS_DIR.glob("*.md"))
    print(f"Found {len(note_files)} notes in {PAPERS_DIR}\n")

    matched = 0
    updated = 0
    skipped_no_match = 0
    skipped_already_filled = 0

    for note_path in note_files:
        try:
            post = frontmatter.load(note_path)
        except Exception as e:
            print(f"  Skipping {note_path.name}: parse error ({e})")
            continue

        citekey = str(post.metadata.get("zotero_key", "")).strip()
        if not citekey or citekey not in papers:
            skipped_no_match += 1
            continue

        matched += 1
        data = papers[citekey]
        changed = False

        for field in FIELDS:
            current = post.metadata.get(field, [])
            # Preserve manual edits unless --force
            if current and not FORCE:
                continue
            if data[field] != current:
                post.metadata[field] = data[field]
                changed = True

        if changed:
            if DRY_RUN:
                print(f"  [DRY] Would update: {note_path.name}")
            else:
                with open(note_path, "wb") as f:
                    frontmatter.dump(post, f)
                print(f"  Updated: {note_path.name}")
            updated += 1
        else:
            skipped_already_filled += 1

    print(f"\n{'='*60}")
    print(f"Notes total:              {len(note_files)}")
    print(f"Matched papers.db entry:  {matched}")
    print(f"Updated:                  {updated}")
    print(f"Skipped (no match):       {skipped_no_match}")
    print(f"Skipped (already filled): {skipped_already_filled}")
    if DRY_RUN:
        print("\nDRY RUN — no files changed")


if __name__ == "__main__":
    main()