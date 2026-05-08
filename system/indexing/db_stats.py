"""Quick stats on papers.db."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "papers.db"
conn = sqlite3.connect(DB)

total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
no_pdf = conn.execute("SELECT COUNT(*) FROM papers WHERE source_type='no_pdf'").fetchone()[0]
indexed = conn.execute("SELECT COUNT(*) FROM papers WHERE source_type IN ('pdf','html')").fetchone()[0]
other = total - no_pdf - indexed

print(f"Total rows in papers.db: {total}")
print(f"  Fully indexed (pdf/html): {indexed}")
print(f"  No-PDF cache:             {no_pdf}")
print(f"  Other/null source_type:   {other}")