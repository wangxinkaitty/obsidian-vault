"""
Strict typo-only theme consolidation with auto-backup.

Default: DeepSeek Flash (cheap, fast, fine for small theme vocabulary).
Toggle USE_SONNET = True to switch to Anthropic Sonnet.

Three defenses against bad merges:
1. Strict typo-only prompt with forbidden examples
2. Validation rejects bad merges (canonical missing, wrong direction, circular)
3. Auto-backup of papers.db before any write

Usage:
    python consolidate_themes.py --dry-run
    python consolidate_themes.py
    python consolidate_themes.py --auto

Restore from backup if a run goes wrong:
    copy papers.db.backup-<timestamp> papers.db
    python bridge_papers.py --force
"""

import os
import re
import sys
import json
import time
import shutil
import sqlite3
from datetime import datetime
from collections import Counter, defaultdict
from dotenv import load_dotenv
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
LOG_PATH = "theme_consolidations.log"

DRY_RUN = "--dry-run" in sys.argv
AUTO = "--auto" in sys.argv

USE_SONNET = False  # Default: DeepSeek Flash. Toggle True for Sonnet.

if USE_SONNET:
    llm = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
        timeout=120.0,
    )
    MODEL = "claude-sonnet-4-5"
    USE_RESPONSE_FORMAT = False
else:
    llm = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        timeout=120.0,
    )
    MODEL = "deepseek-chat"
    USE_RESPONSE_FORMAT = True


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


# ─── Strict typo-only prompt for themes ───────────────────────────
PROMPT = """You are doing TYPO DETECTION on a theme vocabulary. NOT consolidation, NOT organization, NOT taxonomy-building. Just typos.

Themes are broad research-area categories (lowercase-hyphenated). Each paper has 1-2 of them.

Your ONLY job: find themes that refer to the SAME LITERAL CATEGORY with trivial formatting differences.

ALLOWED MERGES (typos only):
- Punctuation: "cog-neuro" / "cog_neuro"
- Plurality: "language-model" / "language-models"
- Abbreviation: "rl" / "reinforcement-learning"
- Hyphenation: "cog-neuro" / "cognitive-neuroscience" (only if clearly the same thing)
- Spelling: "alignement" / "alignment"

FORBIDDEN MERGES — never propose these:
- Adjacent areas: "cognitive-neuroscience" is NOT a duplicate of "computational-cognition"
- Related: "ai-safety" is NOT a duplicate of "ai-policy"
- Subfield → parent: "deep-learning" is NOT a duplicate of "machine-learning"
- Specific → general: "language-models" is NOT a duplicate of "machine-learning"

DECISION CRITERION: Could a careful person read both themes and think "wait, these are literally the same category, just spelled differently"? If YES → merge. If NO → DO NOT MERGE.

DEFAULT TO NOT MERGING.

DIRECTION RULE: Canonical must be the higher-frequency form.
EXISTENCE RULE: Canonical must already exist in the vocabulary list below.

Output a flat JSON dict mapping each typo variant to its canonical:

{"cog-neuro": "cognitive-neuroscience", "rl": "reinforcement-learning"}

If no clear typos found, output: {}

Theme vocabulary (with frequencies):
__THEME_LIST__
"""


def format_theme_list(theme_counts):
    return "\n".join(f"  {theme} ({count})" for theme, count in theme_counts.most_common())


# ─── Robust JSON extraction ─────────────────────────────────────────
def extract_json_dict(content):
    if not content or not content.strip():
        raise ValueError("Empty content")
    text = content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON. First 500 chars: {repr(text[:500])}")


# ─── Streaming LLM call ─────────────────────────────────────────────
def propose_consolidation(theme_counts):
    prompt = PROMPT.replace("__THEME_LIST__", format_theme_list(theme_counts))

    kwargs = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": True,
    }
    if USE_RESPONSE_FORMAT:
        kwargs["response_format"] = {"type": "json_object"}

    print("  Streaming: ", end="", flush=True)
    start = time.time()
    content_parts = []
    chunks = 0

    stream = llm.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            content_parts.append(text)
            chunks += 1
            if chunks % 5 == 0:
                print(".", end="", flush=True)

    elapsed = time.time() - start
    print(f" done ({chunks} chunks, {elapsed:.1f}s)")

    content = "".join(content_parts)
    if not content.strip():
        raise ValueError("Empty response")

    raw_mapping = extract_json_dict(content)
    if not isinstance(raw_mapping, dict):
        raise ValueError(f"Expected dict, got {type(raw_mapping).__name__}")

    return {
        k.strip().lower(): v.strip().lower()
        for k, v in raw_mapping.items()
        if isinstance(k, str) and isinstance(v, str)
        and k.strip() and v.strip()
        and k.strip().lower() != v.strip().lower()
    }


# ─── Validation ─────────────────────────────────────────────────────
def validate_merges(raw_mapping, theme_counts):
    valid = {}
    rejected = []
    proposed_variants = set(raw_mapping.keys())

    for variant, canonical in raw_mapping.items():
        if canonical not in theme_counts:
            rejected.append((variant, canonical, "canonical doesn't exist in vocabulary"))
            continue
        if variant not in theme_counts:
            rejected.append((variant, canonical, "variant doesn't exist in vocabulary"))
            continue
        if theme_counts[canonical] < theme_counts[variant]:
            rejected.append((
                variant, canonical,
                f"canonical ({theme_counts[canonical]}) less frequent than variant ({theme_counts[variant]})"
            ))
            continue
        if canonical in proposed_variants:
            rejected.append((
                variant, canonical,
                f"chain or circle: '{canonical}' is also being merged into '{raw_mapping[canonical]}'"
            ))
            continue
        valid[variant] = canonical
    return valid, rejected


def show_rejected(rejected):
    if not rejected:
        return
    print(f"\n{'='*70}")
    print(f"REJECTED MERGES ({len(rejected)}):")
    print(f"{'='*70}")
    for variant, canonical, reason in rejected:
        print(f"  ✗ {variant} → {canonical}")
        print(f"    {reason}")


def show_merges(mapping, theme_counts):
    print(f"\n{'='*70}")
    print(f"VALIDATED MERGES ({len(mapping)} variants → canonical):")
    print(f"{'='*70}\n")
    grouped = defaultdict(list)
    for variant, canonical in mapping.items():
        grouped[canonical].append(variant)
    for canonical in sorted(grouped.keys(), key=lambda c: -theme_counts.get(c, 0)):
        variants = grouped[canonical]
        canon_count = theme_counts.get(canonical, 0)
        print(f"  → {canonical} ({canon_count} papers)")
        for v in sorted(variants, key=lambda x: -theme_counts.get(x, 0)):
            v_count = theme_counts.get(v, 0)
            print(f"      ← {v} ({v_count} papers)")
        print()


# ─── Auto-backup ────────────────────────────────────────────────────
def backup_db():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DB_PATH}.backup-{timestamp}"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


# ─── Apply ──────────────────────────────────────────────────────────
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
            conn.execute(
                "UPDATE papers SET themes = ? WHERE zotero_key = ?",
                (json.dumps(new_themes), zotero_key),
            )
            updated += 1
    conn.commit()
    return updated


def write_log(mapping, applied_count, backup_path):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n=== {datetime.now().isoformat()} ===\n")
        f.write(f"Model: {MODEL}\n")
        f.write(f"Backup: {backup_path}\n")
        f.write(f"Papers updated: {applied_count}\n")
        f.write("Merges applied (after validation):\n")
        for variant, canonical in sorted(mapping.items()):
            f.write(f"  {variant} -> {canonical}\n")


# ─── Main ───────────────────────────────────────────────────────────
def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)

    cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
    if "themes" not in cols:
        print("ERROR: papers.db has no 'themes' column. Run extract_themes.py first.")
        conn.close()
        return

    theme_counts = load_theme_counts(conn)

    if not theme_counts:
        print("No themes in papers.db. Run extract_themes.py first.")
        conn.close()
        return

    print(f"Theme vocabulary: {len(theme_counts)} unique themes")
    print(f"Model: {MODEL}")

    if len(theme_counts) < 3:
        print("Too few themes to consolidate.")
        conn.close()
        return

    print(f"Asking {MODEL} for typo detection...")
    try:
        raw_mapping = propose_consolidation(theme_counts)
    except Exception as e:
        print(f"\nLLM call failed: {e}")
        conn.close()
        return

    if not raw_mapping:
        print("\nNo typos proposed. Vocabulary is clean.")
        conn.close()
        return

    print(f"\n  LLM proposed {len(raw_mapping)} merges. Validating...")
    valid, rejected = validate_merges(raw_mapping, theme_counts)
    print(f"  After validation: {len(valid)} valid, {len(rejected)} rejected")

    show_rejected(rejected)

    if not valid:
        print("\nNo valid merges after filtering.")
        conn.close()
        return

    show_merges(valid, theme_counts)

    if DRY_RUN:
        print("DRY RUN — nothing applied.")
        conn.close()
        return

    if not AUTO:
        confirm = input("Apply these validated merges? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            conn.close()
            return

    # Auto-backup before any write
    backup_path = backup_db()
    print(f"\nBackup created: {backup_path}")
    print("If something goes wrong, restore with:")
    print(f"  copy \"{backup_path}\" \"{DB_PATH}\"")
    print(f"  py bridge_papers.py --force")

    print("\nApplying...")
    updated = apply_consolidation(conn, valid)
    write_log(valid, updated, backup_path)
    print(f"  Updated {updated} papers in papers.db")
    print(f"  Logged to {LOG_PATH}")
    print(f"\nNext: run bridge_papers.py --force to push themes into Obsidian.")

    conn.close()


if __name__ == "__main__":
    main()