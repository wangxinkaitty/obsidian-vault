"""
Post-hoc theme consolidation.

Reads all themes from papers.db, sends the full vocabulary to an LLM, asks for
near-duplicate groupings + canonical forms, then applies the merges across
papers.db.

Themes are coarser-grained than tags — typical libraries have 10-25 distinct
themes (vs. hundreds of tags). Drift is less common but still happens
(e.g., "cog-neuro" vs "cognitive-neuroscience").

Idempotent. --dry-run to preview. Writes to theme_consolidations.log.

Usage:
    python consolidate_themes.py --dry-run     # Preview only
    python consolidate_themes.py               # Interactive: shows merges, asks before applying
    python consolidate_themes.py --auto        # Apply without confirmation
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
LOG_PATH = "theme_consolidations.log"

DRY_RUN = "--dry-run" in sys.argv
AUTO = "--auto" in sys.argv

# Use Sonnet for this — quality matters since themes affect every paper.
# DeepSeek would also work; switch model+base_url+key if preferred.
USE_SONNET = False

if USE_SONNET:
    llm = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
    )
    MODEL = "claude-sonnet-4-5"
else:
    llm = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    MODEL = "deepseek-chat"


# ─── Step 1: Load and count themes ──────────────────────────────────
def load_theme_counts(conn):
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
    return counter


# ─── Step 2: Ask LLM for consolidation proposal ─────────────────────
CONSOLIDATION_PROMPT = """You are consolidating a theme vocabulary from an academic paper library to remove near-duplicates.

The user's research areas: computational cognition, machine learning, reinforcement learning, AI policy. Themes are broad research-area categories (lowercase-hyphenated), each paper having 1-2 of them. Themes are COARSER than tags — they answer "what kind of research is this" rather than "what specifically is it about".

Below is the full theme list with frequencies (count of papers tagged with each).

Identify groups of themes that mean the same thing or are minor variants of each other (e.g., "cog-neuro" and "cognitive-neuroscience"; "rl" and "reinforcement-learning"; "alignment" and "ai-alignment"). For each group:
- Pick a canonical form (prefer the most common, most descriptive, lowercase-hyphenated)
- List all variants that should be merged into it

DO NOT merge themes that represent genuinely different research areas even if they look similar (e.g., "cognitive-neuroscience" and "computational-cognition" are different fields; "ai-safety" and "ai-policy" overlap but are distinct). When in doubt, leave separate.

ONLY merge clear duplicates or trivial variants.

Return ONLY a JSON object with this structure:
{
  "merges": [
    {
      "canonical": "cognitive-neuroscience",
      "merge_from": ["cog-neuro", "cognitive-neurosci", "cognitive_neuroscience"],
      "reasoning": "trivial variants"
    },
    ...
  ]
}

If no merges are warranted, return: {"merges": []}

Theme vocabulary:
{theme_list}
"""


def propose_consolidation(theme_counts):
    theme_list_str = "\n".join(f"  {theme} ({count})" for theme, count in theme_counts.most_common())

    response = llm.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{
            "role": "user",
            "content": CONSOLIDATION_PROMPT.replace("{theme_list}", theme_list_str),
        }],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content.strip())


# ─── Step 3: Build mapping & validate ───────────────────────────────
def build_mapping(merges, theme_counts):
    mapping = {}
    issues = []
    for m in merges:
        canonical = m.get("canonical", "").strip().lower()
        merge_from = [t.strip().lower() for t in m.get("merge_from", [])]
        if not canonical:
            issues.append("Empty canonical in merge group; skipping")
            continue
        for variant in merge_from:
            if variant == canonical:
                continue
            if variant in mapping and mapping[variant] != canonical:
                issues.append(f"Conflict: '{variant}' assigned to both '{mapping[variant]}' and '{canonical}'")
                continue
            mapping[variant] = canonical
    return mapping, issues


def show_merges(mapping, theme_counts, merges):
    print(f"\n{'='*70}")
    print(f"PROPOSED MERGES ({len(merges)} groups, {len(mapping)} variants → canonical):")
    print(f"{'='*70}\n")
    for m in merges:
        canonical = m.get("canonical", "")
        merge_from = m.get("merge_from", [])
        if not merge_from or all(v == canonical for v in merge_from):
            continue
        canon_count = theme_counts.get(canonical, 0)
        print(f"  → {canonical} ({canon_count} papers)")
        for v in merge_from:
            if v == canonical:
                continue
            v_count = theme_counts.get(v, 0)
            if v_count > 0:
                print(f"      ← {v} ({v_count} papers)")
        reasoning = m.get("reasoning", "")
        if reasoning:
            print(f"      reason: {reasoning}")
        print()


# ─── Step 4: Apply mapping ──────────────────────────────────────────
def apply_consolidation(conn, mapping):
    if not mapping:
        return 0
    rows = conn.execute("SELECT zotero_key, themes FROM papers").fetchall()
    updated = 0
    for zotero_key, themes_json in rows:
        try:
            themes = json.loads(themes_json or "[]")
        except json.JSONDecodeError:
            continue
        new_themes = []
        seen = set()
        changed = False
        for t in themes:
            t_clean = t.strip().lower()
            canonical = mapping.get(t_clean, t_clean)
            if canonical not in seen:
                new_themes.append(canonical)
                seen.add(canonical)
            if canonical != t_clean:
                changed = True
        if changed:
            conn.execute("UPDATE papers SET themes = ? WHERE zotero_key = ?",
                         (json.dumps(new_themes), zotero_key))
            updated += 1
    conn.commit()
    return updated


def write_log(mapping, applied_count):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now().isoformat()} ===\n")
        f.write(f"Papers updated: {applied_count}\n")
        f.write("Merges applied:\n")
        for variant, canonical in sorted(mapping.items()):
            f.write(f"  {variant} → {canonical}\n")


# ─── Main ───────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Run index_papers_v2.py first.")
        return

    conn = sqlite3.connect(DB_PATH)

    # Verify themes column exists
    cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
    if "themes" not in cols:
        print("ERROR: papers.db has no 'themes' column. Run extract_themes.py first.")
        conn.close()
        return

    theme_counts = load_theme_counts(conn)

    if not theme_counts:
        print("No themes in papers.db — run extract_themes.py first.")
        conn.close()
        return

    print(f"Theme vocabulary: {len(theme_counts)} unique themes across all papers")

    if len(theme_counts) < 3:
        print("Too few themes to bother consolidating. Index more papers or extract themes first.")
        conn.close()
        return

    print(f"Asking {MODEL} to propose consolidations...")
    try:
        proposal = propose_consolidation(theme_counts)
    except Exception as e:
        print(f"LLM call failed: {e}")
        conn.close()
        return

    merges = proposal.get("merges", [])
    if not merges:
        print("\nNo consolidations proposed. Theme vocabulary is already clean.")
        conn.close()
        return

    mapping, issues = build_mapping(merges, theme_counts)
    if issues:
        print("\nWarnings during mapping construction:")
        for issue in issues:
            print(f"  - {issue}")

    show_merges(mapping, theme_counts, merges)

    if DRY_RUN:
        print("DRY RUN — nothing applied. Re-run without --dry-run to apply.")
        conn.close()
        return

    if not AUTO:
        confirm = input("Apply these merges? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted; no changes made.")
            conn.close()
            return

    print("\nApplying...")
    updated = apply_consolidation(conn, mapping)
    write_log(mapping, updated)
    print(f"  Updated {updated} papers in papers.db")
    print(f"  Logged to {LOG_PATH}")
    print(f"\nNext: run bridge_papers.py --force to propagate consolidated themes into Obsidian frontmatter.")

    conn.close()


if __name__ == "__main__":
    main()