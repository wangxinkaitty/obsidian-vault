"""
Strict typo-only tag consolidation with auto-backup.

Defenses against bad merges:
1. Prompt explicitly frames task as TYPO DETECTION ONLY, with forbidden examples
2. Script validates LLM output (canonical exists, frequency direction, no circles)
3. Auto-backup of papers.db before any write — restore in one command if needed

Idempotent. --dry-run to preview. Logs to tag_consolidations.log.

Usage:
    python consolidate_tags.py --dry-run
    python consolidate_tags.py
    python consolidate_tags.py --auto      # No confirmation prompt

To restore from backup if something goes wrong:
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
LOG_PATH = "tag_consolidations.log"

DRY_RUN = "--dry-run" in sys.argv
AUTO = "--auto" in sys.argv

# Toggle between Sonnet (recommended for accuracy) and DeepSeek Flash (cheaper)
USE_SONNET = True

USE_SONNET = False
USE_DEEPSEEK_PRO = False   # Set True for V4 Pro, False for V4 Flash

if USE_SONNET:
    llm = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
        timeout=120.0,
    )
    MODEL = "claude-sonnet-4-5"
    USE_RESPONSE_FORMAT = False
    DISABLE_THINKING = False
else:
    llm = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        timeout=180.0,
    )
    MODEL = "deepseek-v4-pro" if USE_DEEPSEEK_PRO else "deepseek-chat"
    USE_RESPONSE_FORMAT = True
    DISABLE_THINKING = USE_DEEPSEEK_PRO
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


# ─── Strict typo-only prompt ───────────────────────────────────────
PROMPT = """You are doing TYPO DETECTION on a tag vocabulary. NOT consolidation, NOT organization, NOT taxonomy-building. Just typos.

Your ONLY job: find tags that refer to the SAME LITERAL CONCEPT with trivial formatting differences.

ALLOWED MERGES (typos only):
- Punctuation: "kl-divergence" / "kl_divergence" / "kl divergence"
- Plurality: "neural-network" / "neural-networks"
- Abbreviation: "rl" / "reinforcement-learning"
- Hyphenation drift: "metacognition" / "meta-cognition"
- Spelling variant: "synesthesia" / "synaesthesia"

FORBIDDEN MERGES — never propose these even if you're tempted:
- Subfield → parent: "cognitive-psychology" is NOT a duplicate of "psychology"
- Specific → category: "psilocybin" is NOT a duplicate of "psychedelics"
- Method → application: "sequence-to-sequence" is NOT a duplicate of "machine-translation"
- Related concept: "connectionism" is NOT a duplicate of "neural-networks"
- Broader → narrower: "evolution" is NOT a duplicate of "human-evolution"

DECISION CRITERION: Could a careful person read both tags and think "wait, these are literally the same word/phrase, just spelled differently"? If YES → merge. If NO → DO NOT MERGE.

DEFAULT TO NOT MERGING. It's better to miss a typo than to corrupt the vocabulary by merging distinct concepts.

DIRECTION RULE: The canonical must be the higher-frequency form. NEVER pick a low-frequency tag as canonical.

EXISTENCE RULE: The canonical must already exist in the vocabulary list below. Never invent a canonical name.

Output a flat JSON dict mapping each typo variant to its canonical:

{"rl": "reinforcement-learning", "kl_divergence": "kl-divergence"}

If no clear typos found, output: {}

Be CONSERVATIVE. Most of these tags should stay as-is. Aim for 0-50 merges, not hundreds.

Tag vocabulary (with frequencies):
__TAG_LIST__
"""


def format_tag_list(tag_counts):
    return "\n".join(f"  {tag} ({count})" for tag, count in tag_counts.most_common())


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
def propose_consolidation(tag_counts):
    prompt = PROMPT.replace("__TAG_LIST__", format_tag_list(tag_counts))

    kwargs = {
        "model": MODEL,
        "max_tokens": 8192,
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
    print("\n  (waiting for first token, can take 30-60s with V4 Pro)...", end="", flush=True)
    stream = llm.chat.completions.create(**kwargs)
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None)
        if text:
            content_parts.append(text)
            chunks += 1
            if chunks % 10 == 0:
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
def validate_merges(raw_mapping, tag_counts):
    """Filter out bad merges. Returns (valid_mapping, rejected_list)."""
    valid = {}
    rejected = []
    proposed_variants = set(raw_mapping.keys())

    for variant, canonical in raw_mapping.items():
        if canonical not in tag_counts:
            rejected.append((variant, canonical, "canonical doesn't exist in vocabulary"))
            continue
        if variant not in tag_counts:
            rejected.append((variant, canonical, "variant doesn't exist in vocabulary"))
            continue
        if tag_counts[canonical] < tag_counts[variant]:
            rejected.append((
                variant, canonical,
                f"canonical ({tag_counts[canonical]}) less frequent than variant ({tag_counts[variant]})"
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
    print(f"REJECTED MERGES ({len(rejected)}) — failed validation:")
    print(f"{'='*70}")
    for variant, canonical, reason in rejected:
        print(f"  ✗ {variant} → {canonical}")
        print(f"    {reason}")


def show_merges(mapping, tag_counts):
    print(f"\n{'='*70}")
    print(f"VALIDATED MERGES ({len(mapping)} variants → canonical):")
    print(f"{'='*70}\n")
    grouped = defaultdict(list)
    for variant, canonical in mapping.items():
        grouped[canonical].append(variant)
    for canonical in sorted(grouped.keys(), key=lambda c: -tag_counts.get(c, 0)):
        variants = grouped[canonical]
        canon_count = tag_counts.get(canonical, 0)
        print(f"  → {canonical} ({canon_count} papers)")
        for v in sorted(variants, key=lambda x: -tag_counts.get(x, 0)):
            v_count = tag_counts.get(v, 0)
            print(f"      ← {v} ({v_count} papers)")
        print()


# ─── Auto-backup ────────────────────────────────────────────────────
def backup_db():
    """Backup papers.db with timestamp before applying changes."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{DB_PATH}.backup-{timestamp}"
    shutil.copy2(DB_PATH, backup_path)
    return backup_path


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
            conn.execute(
                "UPDATE papers SET tags = ? WHERE zotero_key = ?",
                (json.dumps(new_tags), zotero_key),
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
    tag_counts = load_tag_counts(conn)

    if not tag_counts:
        print("No tags in papers.db.")
        return

    print(f"Tag vocabulary: {len(tag_counts)} unique tags")
    print(f"Model: {MODEL}")

    if len(tag_counts) < 5:
        print("Too few tags to consolidate.")
        return

    print(f"Asking {MODEL} for typo detection...")
    try:
        raw_mapping = propose_consolidation(tag_counts)
    except Exception as e:
        print(f"\nLLM call failed: {e}")
        return

    if not raw_mapping:
        print("\nNo typos proposed. Vocabulary is clean.")
        return

    print(f"\n  LLM proposed {len(raw_mapping)} merges. Validating...")
    valid, rejected = validate_merges(raw_mapping, tag_counts)
    print(f"  After validation: {len(valid)} valid, {len(rejected)} rejected")

    show_rejected(rejected)

    if not valid:
        print("\nNo valid merges after filtering. Nothing to apply.")
        return

    show_merges(valid, tag_counts)

    if DRY_RUN:
        print("DRY RUN — nothing applied.")
        return

    if not AUTO:
        confirm = input("Apply these validated merges? [y/N]: ").strip().lower()
        if confirm != "y":
            print("Aborted.")
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
    print(f"\nNext: run bridge_papers.py --force to push consolidated tags into Obsidian.")

    conn.close()


if __name__ == "__main__":
    main()