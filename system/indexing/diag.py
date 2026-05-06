"""Diagnostic: compare papers.db data vs Obsidian frontmatter for each paper note."""

import sqlite3
import json
from pathlib import Path
import frontmatter

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_ROOT = SCRIPT_DIR.parent.parent
PAPERS_DIR = VAULT_ROOT / "Notes" / "Papers"
DB_PATH = SCRIPT_DIR / "papers.db"

conn = sqlite3.connect(str(DB_PATH))
db_rows = conn.execute("""
    SELECT citekey, summary, methods, datasets, key_claims, limitations, tags
    FROM papers WHERE citekey IS NOT NULL AND citekey != ''
""").fetchall()
db = {r[0]: r for r in db_rows}
print(f"papers.db: {len(db)} papers with citekey\n")

for note_path in sorted(PAPERS_DIR.glob("*.md")):
    print(f"{'='*70}\n{note_path.name}")
    try:
        post = frontmatter.load(note_path)
    except Exception as e:
        print(f"  PARSE ERROR: {e}")
        continue

    citekey = str(post.metadata.get("zotero_key", "")).strip()
    print(f"  citekey: {repr(citekey)}")

    if citekey not in db:
        print(f"  NOT IN papers.db")
        continue

    print(f"  IN papers.db")
    db_row = db[citekey]
    fields = ["summary", "methods", "datasets", "key_claims", "limitations", "tags"]

    for i, f in enumerate(fields, start=1):
        current = post.metadata.get(f)
        db_raw = db_row[i]
        print(f"\n  {f}:")
        print(f"    frontmatter: type={type(current).__name__}, value={repr(current)[:90]}")
        print(f"    papers.db:   type={type(db_raw).__name__}, value={repr(db_raw)[:90]}")

print(f"\n{'='*70}")
conn.close()