"""
Dump theme vocabulary alphabetically with frequencies.

Usage:
    py dump_themes.py
    py dump_themes.py > themes.txt
"""

import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("papers.db")
counts = Counter()
for (t,) in conn.execute("SELECT themes FROM papers WHERE themes IS NOT NULL"):
    for theme in json.loads(t or "[]"):
        counts[theme.strip().lower()] += 1

print(f"Total unique themes: {len(counts)}\n")
for theme, n in sorted(counts.items()):
    print(f"  {theme} ({n})")