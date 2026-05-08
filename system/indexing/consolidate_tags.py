"""
Post-hoc tag consolidation using DeepSeek V4 Pro with streaming.

Shows live progress as the LLM generates output. Each '.' = content chunk
received, each '·' = reasoning chunk (if thinking is enabled).

Idempotent. --dry-run to preview. Logs to tag_consolidations.log.

Usage:
    python consolidate_tags.py --dry-run
    python consolidate_tags.py
    python consolidate_tags.py --auto
"""

import os
import re
import sys
import json
import time
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

USE_SONNET = False

if USE_SONNET:
    llm = OpenAI(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        base_url="https://api.anthropic.com/v1/",
    )
    MODEL = "claude-sonnet-4-5"
    USE_RESPONSE_FORMAT = False
    USE_DEEPSEEK_THINKING = False
else:
    llm = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    MODEL = "deepseek-v4-pro"
    USE_RESPONSE_FORMAT = True
    USE_DEEPSEEK_THINKING = True


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
PROMPT = """You are consolidating a tag vocabulary from an academic paper library.

The user's research areas: computational cognition, machine learning, reinforcement learning, AI policy. Tags are lowercase-hyphenated.

Below is the full tag vocabulary with frequencies. Identify near-duplicate tags — same concept under slightly different names (e.g., "rl" vs "reinforcement-learning"; "neural-net" vs "neural-networks"; "kl_divergence" vs "kl-divergence").

For each duplicate variant, map it to the canonical form (most common, descriptive, lowercase-hyphenated).

DO NOT merge genuinely different concepts even if similar (e.g., "model-based-rl" vs "model-free-rl" are different; "attention-mechanism" vs "self-attention" are arguably different).

ONLY include variants that should be merged. Tags that should stay as-is should be OMITTED.

Output a flat JSON dictionary mapping variant -> canonical:

{"rl": "reinforcement-learning", "neural_net": "neural-networks"}

If no merges warranted, output: {}

Tag vocabulary:
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
    raise ValueError(f"Could not extract valid JSON. First 500 chars: {repr(text[:500])}")


# ─── Streaming LLM call with progress ───────────────────────────────
def propose_consolidation(tag_counts):
    prompt = PROMPT.replace("__TAG_LIST__", format_tag_list(tag_counts))

    kwargs = {
        "model": MODEL,
        "max_tokens": 32768,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": True,
    }
    if USE_RESPONSE_FORMAT:
        kwargs["response_format"] = {"type": "json_object"}

    extra_body = {}
    if USE_DEEPSEEK_THINKING:
        extra_body["thinking"] = {"type": "disabled"}
    if extra_body:
        kwargs["extra_body"] = extra_body

    print("  Streaming: ", end="", flush=True)
    start = time.time()

    content_parts = []
    reasoning_parts = []
    content_chunks = 0
    reasoning_chunks = 0

    try:
        stream = llm.chat.completions.create(**kwargs)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Content chunk
            text = getattr(delta, "content", None)
            if text:
                content_parts.append(text)
                content_chunks += 1
                if content_chunks % 10 == 0:
                    print(".", end="", flush=True)

            # Reasoning chunk (V4 Pro thinking mode)
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                reasoning_parts.append(reasoning)
                reasoning_chunks += 1
                if reasoning_chunks % 10 == 0:
                    print("·", end="", flush=True)
    except Exception as e:
        print(f"\n  Stream error: {e}")
        raise

    elapsed = time.time() - start
    print(f" done ({content_chunks} content, {reasoning_chunks} reasoning chunks, {elapsed:.1f}s)")

    content = "".join(content_parts)
    reasoning = "".join(reasoning_parts)

    if not content.strip():
        if reasoning.strip():
            print("  (using reasoning_content fallback)")
            content = reasoning
        else:
            raise ValueError("Both content and reasoning are empty")

    mapping = extract_json_dict(content)

    if not isinstance(mapping, dict):
        raise ValueError(f"Expected dict, got {type(mapping).__name__}")

    return {
        k.strip().lower(): v.strip().lower()
        for k, v in mapping.items()
        if isinstance(k, str) and isinstance(v, str)
        and k.strip() and v.strip()
        and k.strip().lower() != v.strip().lower()
    }


# ─── Display ────────────────────────────────────────────────────────
def show_merges(mapping, tag_counts):
    print(f"\n{'='*70}")
    print(f"PROPOSED MERGES ({len(mapping)} variants → canonical):")
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
        print(f"\nLLM call failed: {e}")
        return

    if not mapping:
        print("\nNo consolidations proposed. Vocabulary is already clean.")
        return

    show_merges(mapping, tag_counts)

    if DRY_RUN:
        print("DRY RUN — nothing applied.")
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