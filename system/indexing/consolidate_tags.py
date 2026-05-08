"""
Post-hoc tag consolidation.

One LLM call. Asks for a flat JSON mapping {variant: canonical}, which is much
more compact than structured merge groups, so the response fits in 8K output
tokens even for vocabularies of 1000+ tags.

After the LLM returns the mapping, the script groups variants by canonical for
display, applies the consolidation to papers.db, and logs the operation.

Idempotent. --dry-run to preview. Logs to tag_consolidations.log.

Usage:
    python consolidate_tags.py --dry-run   # Preview
    python consolidate_tags.py             # Interactive: confirm before applying
    python consolidate_tags.py --auto      # Apply without confirmation
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from collections import Counter, defaultdict
from dotenv import load_dotenv
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
LOG_PATH = "tag_consolidations.log"

DRY_RUN = "--dry-run" in sys.argv
AUTO = "--auto" in sys.argv

USE_SONNET = False  # Set True if you have ANTHROPIC_API_KEY

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
    MODEL = "deepseek-v4-pro"


# ─── Step 1: Load and count tags ────────────────────────────────────
def load_tag_counts(conn):
    counter = Counter()
    rows = conn.execute("SELECT tags FROM papers").fetchall()
    for (tags_json,) in rows:
        try:
            for t in json.loads(tags_json or "[]"):
                t_clean = t.strip().lower()
                if t_clean:
                    counter[t_clean] += 1
        except json.JSONDecodeError:
            continue
    return counter


# ─── Prompt ─────────────────────────────────────────────────────────
PROMPT = """You are consolidating a tag vocabulary from an academic paper library to remove near-duplicates.

The user's research areas: computational cognition, machine learning, reinforcement learning, AI policy. Tags should be lowercase-hyphenated.

Below is the full tag vocabulary with frequencies. Identify near-duplicate tags — same concept under slightly different names (e.g., "rl" vs "reinforcement-learning"; "neural-net" vs "neural-networks"; "transformer" vs "transformers"; "kl_divergence" vs "kl-divergence").

For each duplicate variant, map it to the canonical form (prefer the most common, most descriptive, lowercase-hyphenated form).

DO NOT merge genuinely different concepts even if similar (e.g., "model-based-rl" and "model-free-rl" are different; "attention-mechanism" and "self-attention" are arguably different — leave them separate unless clearly redundant).

ONLY include variants that should be merged. Tags that should stay as-is should be OMITTED from your output.

Return ONLY a JSON object — a flat dictionary mapping each variant to its canonical form:

{
  "rl": "reinforcement-learning",
  "reinforcement_learning": "reinforcement-learning",
  "neural_net": "neural-networks",
  "transformer": "transformers"
}

If no merges warranted, return: {}

Tag vocabulary:
__TAG_LIST__
"""


def format_tag_list(tag_counts):
    return "\n".join(f"  {tag} ({count})" for tag, count in tag_counts.most_common())


# ─── LLM call ───────────────────────────────────────────────────────
def propose_consolidation(tag_counts):
    prompt = PROMPT.replace("__TAG_LIST__", format_tag_list(tag_counts))

    response = llm.chat.completions.create(
        model=MODEL,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
    mapping = json.loads(content.strip())

    # Normalize to lowercase, strip
    return {
        k.strip().lower(): v.strip().lower()
        for k, v in mapping.items()
        if k.strip() and v.strip() and k.strip().lower() != v.strip().lower()
    }


# ─── Display: group variants by canonical ──────────────────────────
def show_merges(mapping, tag_counts):
    print(f"\n{'='*70}")
    print(f"PROPOSED MERGES ({len(mapping)} variants → canonical):")
    print(f"{'='*70}\n")

    # Group: canonical → list of variants
    grouped = defaultdict(list)
    for variant, canonical in mapping.items():
        grouped[canonical].append(variant)

    # Sort groups by canonical's frequency
    for canonical in sorted(grouped.keys(), key=lambda c: -tag_counts.get(c, 0)):
        variants = grouped[canonical]
        canon_count = tag_counts.get(canonical, 0)
        print(f"  → {canonical} ({canon_count} papers)")
        for v in sorted(variants, key=lambda x: -tag_counts.get(x, 0)):
            v_count = tag_counts.get(v, 0)
            print(f"      ← {v} ({v_count} papers)")
        print()


# ─── Apply mapping ──────────────────────────────────────────────────
def apply_consolidation(conn, mapping):
    if not mapping:
        return 0
    rows = conn.execute("SELECT zotero_key, tags FROM papers").fetchall()
    updated = 0
    for zotero_key, tags_json in rows:
        try:
            tags = json.loads(tags_json or "[]")
        except json.JSONDecodeError:
            continue
        new_tags = []
        seen = set()
        changed = False
        for t in tags:
            t_clean = t.strip().lower()
            canonical = mapping.get(t_clean, t_clean)
            if canonical not in seen:
                new_tags.append(canonical)
                seen.add(canonical)
            if canonical != t_clean:
                changed = True
        if changed:
            conn.execute("UPDATE papers SET tags = ? WHERE zotero_key = ?",
                         (json.dumps(new_tags), zotero_key))
            updated += 1
    conn.commit()
    return updated


def write_log(mapping, applied_count):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now().isoformat()} ===\n")
        f.write(f"Papers updated: {applied_count}\n")
        f.write("Merges applied:\n")
        for variant, canonical in sorted(mapping.items()):
            f.write(f"  {variant} -> {canonical}\n")


# ─── Main ───────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    tag_counts = load_tag_counts(conn)

    if not tag_counts:
        print("No tags in papers.db.")
        return

    print(f"Tag vocabulary: {len(tag_counts)} unique tags")

    if len(tag_counts) < 5:
        print("Too few tags to bother consolidating.")
        return

    print(f"Asking {MODEL} for consolidation mapping...")
    try:
        mapping = propose_consolidation(tag_counts)
    except Exception as e:
        print(f"LLM call failed: {e}")
        return

    if not mapping:
        print("\nNo consolidations proposed. Vocabulary is already clean.")
        return

    show_merges(mapping, tag_counts)

    if DRY_RUN:
        print("DRY RUN — nothing applied. Re-run without --dry-run to apply.")
        return

    if not AUTO:
        confirm = input("Apply these merges? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    print("\nApplying...")
    updated = apply_consolidation(conn, mapping)
    write_log(mapping, updated)
    print(f"  Updated {updated} papers in papers.db")
    print(f"  Logged to {LOG_PATH}")
    print(f"\nNext: run bridge_papers.py --force to push consolidated tags into Obsidian.")

    conn.close()


if __name__ == "__main__":
    main()