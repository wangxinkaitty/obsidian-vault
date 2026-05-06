"""
Bridge papers.db → Obsidian paper-note frontmatter.

Reads structured metadata from papers.db and fills empty fields in
matching Obsidian paper notes. Preserves manual edits by default.

Match key: citekey, stored as `zotero_key` in Obsidian frontmatter.

Dynamically loads columns based on FIELDS list and what's available in papers.db
— gracefully handles fields that may not yet exist (e.g., themes before
extract_themes.py has run).

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

# Fields to sync from papers.db into note frontmatter.
# Add or remove as your schema evolves.
FIELDS = ["summary", "methods", "datasets", "key_claims", "limitations", "tags", "themes"]

# Which fields are plain strings vs JSON-encoded lists in papers.db
STRING_FIELDS = {"summary"}


# ─── Load papers.db ─────────────────────────────────────────────────
def load_papers():
    conn = sqlite3.connect(str(DB_PATH))

    # Check which columns actually exist in papers.db
    available_cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
    if "citekey" not in available_cols:
        conn.close()
        raise RuntimeError("papers.db has no 'citekey' column")

    # Only select FIELDS that exist as columns
    select_fields = [f for f in FIELDS if f in available_cols]
    missing = [f for f in FIELDS if f not in available_cols]
    if missing:
        print(f"Note: papers.db missing columns for fields {missing}; will skip them")

    sql_cols = ["citekey"] + select_fields
    sql = f"SELECT {', '.join(sql_cols)} FROM papers WHERE citekey IS NOT NULL AND citekey != ''"
    rows = conn.execute(sql).fetchall()
    conn.close()

    papers = {}
    for row in rows:
        citekey = (row[0] or "").strip()
        if not citekey:
            continue
        data = {}
        for i, field in enumerate(select_fields, start=1):
            raw = row[i]
            if field in STRING_FIELDS:
                data[field] = raw or ""
            else:
                try:
                    data[field] = json.loads(raw) if raw else []
                except (json.JSONDecodeError, TypeError):
                    data[field] = []
        # Fill defaults for any FIELDS that weren't loaded (missing column)
        for field in FIELDS:
            if field not in data:
                data[field] = "" if field in STRING_FIELDS else []
        papers[citekey] = data
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
            current = post.metadata.get(field)
            # "Empty" check works for both strings ("") and lists ([])
            current_is_empty = current is None or current == "" or current == []
            # Preserve manual edits unless --force
            if not current_is_empty and not FORCE:
                continue
            new_value = data.get(field, "" if field in STRING_FIELDS else [])
            if new_value != current:
                post.metadata[field] = new_value
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