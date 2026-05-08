import sqlite3, json
from collections import Counter
conn = sqlite3.connect("papers.db")
counts = Counter()
for (t,) in conn.execute("SELECT tags FROM papers"):
    for tag in json.loads(t or "[]"):
        counts[tag] += 1
for tag, n in sorted(counts.items()):
    print(f"  {tag} ({n})")