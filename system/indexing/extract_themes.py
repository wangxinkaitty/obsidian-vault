"""
Emergent theme assignment.

Reads each paper's structured metadata from papers.db (title, summary, key claims,
tags) and asks the LLM to assign 1-2 broad research themes — free-form, in the
paper's own framing. The theme vocabulary grows as the script runs; later papers
see earlier themes and reuse them when applicable.

After running, use consolidate_themes.py (or generalized consolidate_tags.py)
to canonicalize near-duplicates.

Cheap: uses existing structured data, not the PDF. ~$0.05 per 500 papers on Flash.

Usage:
    python extract_themes.py                # Process papers without themes
    python extract_themes.py --reassign     # Force reassign all papers
"""

import os
import sys
import json
import sqlite3
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
VOCAB_TOP_N = 25            # top themes to show LLM as preferred vocabulary
VOCAB_REFRESH_EVERY = 25    # rebuild vocabulary every N processed papers

REASSIGN = "--reassign" in sys.argv

llm = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)
MODEL = "deepseek-chat"


# ─── Database setup ─────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
    if "themes" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN themes TEXT")
        conn.commit()
    return conn


def load_theme_vocabulary(conn):
    """Top themes from papers.db, ordered by frequency."""
    counter = Counter()
    rows = conn.execute("SELECT themes FROM papers WHERE themes IS NOT NULL").fetchall()
    for (themes_json,) in rows:
        try:
            for t in json.loads(themes_json or "[]"):
                t_clean = t.strip().lower()
                if t_clean:
                    counter[t_clean] += 1
        except json.JSONDecodeError:
            continue
    return [t for t, _ in counter.most_common(VOCAB_TOP_N)]


# ─── LLM theme extraction ───────────────────────────────────────────
THEME_PROMPT = """You assign broad research themes to academic papers based on their structured metadata.

Given a paper's title, summary, key claims, and existing tags, output 1-2 broad themes that capture WHAT KIND OF RESEARCH this is (not what it's about specifically — that's what tags are for).

Themes are coarse-grained categories like: reinforcement-learning, computational-cognition, ai-safety, language-models, cognitive-neuroscience, decision-making, etc.

Tags are fine-grained: "successor-representation", "graph-attention-networks", "transformer-circuits".
Themes are big buckets: "reinforcement-learning", "machine-learning-theory".

Format: lowercase-hyphenated. Pick 1 if the paper is squarely in one area; pick 2 only if the paper genuinely bridges two distinct fields.

THEME CONSISTENCY: Strongly prefer reusing themes from this existing vocabulary when applicable. Only invent a new theme if no existing one fits:
{theme_vocab}

Paper:
- Title: {title}
- Summary: {summary}
- Key claims: {key_claims}
- Existing tags: {tags}

Return ONLY a JSON object:
{{"themes": ["theme-1", "theme-2"]}}

Or if only one theme applies:
{{"themes": ["theme-1"]}}
"""


def extract_themes_for_paper(title, summary, key_claims, tags, vocab):
    vocab_str = ", ".join(vocab) if vocab else "(none yet — invent appropriate themes)"
    response = llm.chat.completions.create(
        model=MODEL,
        messages=[{
            "role": "user",
            "content": THEME_PROMPT.format(
                title=title or "[unknown]",
                summary=summary or "[no summary]",
                key_claims=", ".join(key_claims) if key_claims else "[none]",
                tags=", ".join(tags) if tags else "[none]",
                theme_vocab=vocab_str,
            ),
        }],
        response_format={"type": "json_object"},
        temperature=0,
    )
    result = json.loads(response.choices[0].message.content)
    themes = result.get("themes", [])
    return [t.strip().lower() for t in themes if t and t.strip()]


# ─── Main ───────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Run index_papers_v2.py first.")
        return

    conn = init_db()
    vocab = load_theme_vocabulary(conn)
    print(f"Starting theme vocabulary: {len(vocab)} themes")
    if REASSIGN:
        print("REASSIGN MODE: will reprocess all papers, including those already themed")

    # Fetch papers needing themes
    if REASSIGN:
        rows = conn.execute("""
            SELECT zotero_key, title, summary, key_claims, tags FROM papers
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT zotero_key, title, summary, key_claims, tags FROM papers
            WHERE themes IS NULL OR themes = '' OR themes = '[]'
        """).fetchall()

    print(f"Papers to process: {len(rows)}\n")

    processed = 0
    failed = 0

    for i, (zotero_key, title, summary, claims_json, tags_json) in enumerate(rows, start=1):
        try:
            key_claims = json.loads(claims_json or "[]")
            tags = json.loads(tags_json or "[]")
        except json.JSONDecodeError:
            key_claims, tags = [], []

        print(f"[{i}/{len(rows)}] {(title or '[untitled]')[:75]}")

        try:
            themes = extract_themes_for_paper(title, summary, key_claims, tags, vocab)
        except Exception as e:
            print(f"    LLM call failed: {e}")
            failed += 1
            continue

        if not themes:
            print(f"    No themes returned; skipping")
            failed += 1
            continue

        conn.execute("UPDATE papers SET themes = ? WHERE zotero_key = ?",
                     (json.dumps(themes), zotero_key))
        conn.commit()
        processed += 1
        print(f"    ✓ {', '.join(themes)}")

        # Refresh vocabulary periodically so newly-discovered themes propagate
        if processed % VOCAB_REFRESH_EVERY == 0:
            vocab = load_theme_vocabulary(conn)

    print(f"\n{'='*60}")
    print(f"Done. Processed: {processed}, failed: {failed}")

    # Final vocabulary summary
    final_vocab = load_theme_vocabulary(conn)
    print(f"\nFinal theme vocabulary ({len(final_vocab)} themes, top {min(VOCAB_TOP_N, len(final_vocab))}):")
    counter = Counter()
    rows = conn.execute("SELECT themes FROM papers WHERE themes IS NOT NULL").fetchall()
    for (themes_json,) in rows:
        try:
            for t in json.loads(themes_json or "[]"):
                counter[t.strip().lower()] += 1
        except json.JSONDecodeError:
            continue
    for theme, count in counter.most_common():
        print(f"  {count:3d}  {theme}")

    print(f"\nNext: review the vocabulary. If you see near-duplicates, run consolidate_tags.py")
    print(f"      adapted for themes (or modify it to point at the 'themes' column).")
    print(f"      Then run bridge_papers.py to push themes into Obsidian frontmatter.")

    conn.close()


if __name__ == "__main__":
    main()