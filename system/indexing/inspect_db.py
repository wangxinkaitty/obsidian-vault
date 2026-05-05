"""Quick inspection of indexed papers."""
import sqlite3
import json

conn = sqlite3.connect("papers.db")
rows = conn.execute("""
    SELECT title, authors, year, source_type, methods, datasets, key_claims, limitations, tags
    FROM papers
""").fetchall()

for title, authors, year, source, methods, datasets, claims, limits, tags in rows:
    print("\n" + "=" * 70)
    print(f"{title}")
    print(f"  {authors} ({year}) — source: {source}")
    print(f"\n  Methods:    {', '.join(json.loads(methods))}")
    print(f"  Datasets:   {', '.join(json.loads(datasets)) or '—'}")
    print(f"  Tags:       {', '.join(json.loads(tags))}")
    print(f"\n  Key claims:")
    for c in json.loads(claims):
        print(f"    - {c}")
    if json.loads(limits):
        print(f"\n  Limitations:")
        for l in json.loads(limits):
            print(f"    - {l}")

conn.close()