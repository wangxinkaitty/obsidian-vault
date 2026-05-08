"""
Paper indexing pipeline — v2.

Improvements over v1:
- PyMuPDF (fitz) for cleaner PDF text extraction (better on multi-column papers)
- Smarter text selection: first chunk (abstract + intro) + last chunk (conclusion),
  skipping noisy middle sections
- Added `summary` field (2-sentence overview)
- Tightened extraction prompt (used vs referenced datasets; specific methods)
- Tag consistency: loads existing tag vocabulary and hints LLM to reuse
- No-PDF cache: papers without a PDF/HTML attachment are marked once and skipped
  on subsequent runs. Use --retry-no-pdf to clear the cache.
- Incremental sync: only fetches Zotero items modified since last successful run.
  Use --full-sync to force a complete re-fetch.

Backward compatible with v1 papers.db. Adds `summary` column if missing.

Usage:
    python index_papers_v2.py                 # Incremental: fetch only changed items
    python index_papers_v2.py --full-sync     # Re-fetch entire Zotero library
    python index_papers_v2.py --reindex       # Force re-extraction of all papers
    python index_papers_v2.py --reindex-empty # Re-extract papers where v1 left fields empty
    python index_papers_v2.py --retry-no-pdf  # Clear no-PDF cache and re-check those papers
"""

import os
import sys
import json
import sqlite3
import tempfile
from datetime import datetime
from collections import Counter
from dotenv import load_dotenv
from pyzotero import zotero
import fitz  # PyMuPDF
from bs4 import BeautifulSoup
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
TEST_LIMIT = None

HEAD_CHARS = 8000
TAIL_CHARS = 4000
MAX_PDF_PAGES = 40

TAG_VOCAB_TOP_N = 60

REINDEX_ALL = "--reindex" in sys.argv
REINDEX_EMPTY = "--reindex-empty" in sys.argv
RETRY_NO_PDF = "--retry-no-pdf" in sys.argv
FULL_SYNC = "--full-sync" in sys.argv

ZOTERO_DATA_DIR = os.path.expanduser("~/Zotero")

EXIT_NEW_INDEXED = 0
EXIT_NOTHING_NEW = 10
EXIT_FATAL = 1

# ─── API clients ────────────────────────────────────────────────────
zot = zotero.Zotero(
    library_id=os.getenv("ZOTERO_USER_ID"),
    library_type="user",
    api_key=os.getenv("ZOTERO_API_KEY"),
)

llm = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ─── Database ───────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            zotero_key TEXT PRIMARY KEY,
            title TEXT,
            authors TEXT,
            year INTEGER,
            venue TEXT,
            citekey TEXT,
            abstract TEXT,
            methods TEXT,
            datasets TEXT,
            key_claims TEXT,
            limitations TEXT,
            tags TEXT,
            source_type TEXT,
            extracted_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(papers)").fetchall()]
    if "summary" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN summary TEXT")
    if "extraction_version" not in cols:
        conn.execute("ALTER TABLE papers ADD COLUMN extraction_version TEXT")
    conn.commit()
    return conn


def get_last_version(conn):
    row = conn.execute("SELECT value FROM kv WHERE key='zotero_version'").fetchone()
    return int(row[0]) if row else 0


def set_last_version(conn, version):
    conn.execute("INSERT OR REPLACE INTO kv VALUES ('zotero_version', ?)", (str(version),))
    conn.commit()


def already_indexed(conn, zotero_key):
    row = conn.execute(
        "SELECT methods, datasets, key_claims, summary, source_type FROM papers WHERE zotero_key = ?",
        (zotero_key,)
    ).fetchone()
    if not row:
        return False

    methods, datasets, claims, summary, source_type = row

    if source_type == "no_pdf":
        return not RETRY_NO_PDF

    if REINDEX_ALL:
        return False

    if REINDEX_EMPTY:
        try:
            if not json.loads(methods or "[]"):
                return False
            if not json.loads(claims or "[]"):
                return False
            if not summary:
                return False
        except json.JSONDecodeError:
            return False

    return True


def mark_no_pdf(conn, zotero_key, title, authors, year, venue, citekey, abstract):
    conn.execute("""
        INSERT INTO papers (
            zotero_key, title, authors, year, venue, citekey, abstract,
            summary, methods, datasets, key_claims, limitations, tags,
            source_type, extracted_at, extraction_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(zotero_key) DO UPDATE SET
            source_type=excluded.source_type,
            extracted_at=excluded.extracted_at
    """, (
        zotero_key, title, authors, year, venue, citekey, abstract,
        "", "[]", "[]", "[]", "[]", "[]",
        "no_pdf",
        datetime.now().isoformat(),
        "v2",
    ))
    conn.commit()


def load_tag_vocabulary(conn):
    counter = Counter()
    rows = conn.execute(
        "SELECT tags FROM papers WHERE source_type != 'no_pdf' OR source_type IS NULL"
    ).fetchall()
    for (tags_json,) in rows:
        try:
            for t in json.loads(tags_json or "[]"):
                counter[t.strip().lower()] += 1
        except json.JSONDecodeError:
            continue
    return [tag for tag, _ in counter.most_common(TAG_VOCAB_TOP_N)]


# ─── Attachment file resolution ─────────────────────────────────────
def get_attachment_path(attachment_data):
    attachment_key = attachment_data.get("key")
    filename = attachment_data.get("filename")

    if attachment_key and filename:
        local_path = os.path.join(ZOTERO_DATA_DIR, "storage", attachment_key, filename)
        if os.path.exists(local_path):
            return local_path, None

    if not attachment_key:
        return None, None
    try:
        file_bytes = zot.file(attachment_key)
    except Exception as e:
        print(f"    Couldn't fetch via API: {e}")
        return None, None

    suffix = os.path.splitext(filename or "")[1] or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        return tmp.name, tmp.name


# ─── Text extraction (PyMuPDF) ──────────────────────────────────────
def extract_pdf_text(pdf_path):
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"    PyMuPDF open failed: {e}")
        return None

    try:
        page_count = min(len(doc), MAX_PDF_PAGES)
        if page_count == 0:
            return None

        all_text = []
        for i in range(page_count):
            try:
                page_text = doc[i].get_text("text") or ""
                all_text.append(page_text)
            except Exception:
                continue
        full = "\n".join(all_text).strip()
        if not full:
            return None

        if len(full) <= HEAD_CHARS + TAIL_CHARS:
            return full

        head = full[:HEAD_CHARS]
        tail = full[-TAIL_CHARS:]
        return f"{head}\n\n[... middle of paper omitted for brevity ...]\n\n{tail}"

    finally:
        doc.close()


def extract_html_text(html_path):
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        full = "\n".join(lines)
        if len(full) <= HEAD_CHARS + TAIL_CHARS:
            return full
        return full[:HEAD_CHARS] + "\n\n[... middle omitted ...]\n\n" + full[-TAIL_CHARS:]
    except Exception as e:
        print(f"    HTML parsing failed: {e}")
        return None


def get_paper_text(item_key):
    children = zot.children(item_key)
    pdfs = [c for c in children if c["data"].get("contentType") == "application/pdf"]
    htmls = [c for c in children
             if c["data"].get("contentType") in ("text/html", "application/xhtml+xml")]

    if pdfs:
        path, tmp = get_attachment_path(pdfs[0]["data"])
        if path:
            try:
                text = extract_pdf_text(path)
                if text and text.strip():
                    return text, "pdf"
            finally:
                if tmp:
                    try: os.unlink(tmp)
                    except Exception: pass

    if htmls:
        path, tmp = get_attachment_path(htmls[0]["data"])
        if path:
            try:
                text = extract_html_text(path)
                if text and text.strip():
                    return text, "html"
            finally:
                if tmp:
                    try: os.unlink(tmp)
                    except Exception: pass

    return None, None


# ─── LLM extraction ─────────────────────────────────────────────────
EXTRACTION_PROMPT = """You extract structured information from academic papers and articles.

Return ONLY a valid JSON object (no markdown, no commentary) with these fields:

- summary: 2 sentences, plain English, capturing the paper's central contribution and approach. Avoid generic phrases like "this paper presents."
- methods: list of specific techniques or methodologies the paper USES (not just mentions). Be specific: "graph attention networks" not "deep learning"; "successor representation" not "reinforcement learning". 1-6 entries. Empty list only if truly inapplicable (e.g., position papers).
- datasets: list of datasets the paper actually USED for experiments or analysis. Do NOT include datasets only mentioned as related work or comparison points. Be specific: "ImageNet" not "image classification benchmarks". Empty list if no datasets used.
- key_claims: list of 2-4 NOVEL contributions or findings, each one concise sentence in your own words. Skip background facts and standard claims; focus on what THIS paper argues that's new.
- limitations: list of limitations or future work the authors themselves acknowledge. Empty list if none discussed.
- tags: list of 3-7 short topic tags in lowercase-hyphenated style.

TAG CONSISTENCY: Prefer reusing tags from this existing vocabulary when applicable, only inventing new tags if no existing one fits well:
{tag_vocab}

Title: {title}
Authors: {authors}
Abstract: {abstract}

Document text (excerpt — head and tail of paper):
{text}
"""


def extract_metadata(title, authors, abstract, text, tag_vocab):
    vocab_str = ", ".join(tag_vocab) if tag_vocab else "(no existing vocabulary yet)"
    response = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(
                title=title or "[unknown]",
                authors=authors or "[unknown]",
                abstract=abstract or "[no abstract]",
                text=text,
                tag_vocab=vocab_str,
            ),
        }],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(response.choices[0].message.content)


# ─── Helpers ────────────────────────────────────────────────────────
def parse_authors(creators):
    return ", ".join(
        f"{c.get('firstName', '')} {c.get('lastName', '')}".strip()
        for c in creators
        if c.get("creatorType") == "author"
    )


def parse_citekey(extra):
    if not extra or "Citation Key:" not in extra:
        return ""
    return extra.split("Citation Key:")[1].strip().split("\n")[0].strip()


def safe_year(date_str):
    if not date_str:
        return None
    year_str = date_str[:4]
    return int(year_str) if year_str.isdigit() else None


# ─── Main ───────────────────────────────────────────────────────────
def main():
    conn = init_db()

    if RETRY_NO_PDF:
        cleared = conn.execute(
            "DELETE FROM papers WHERE source_type = 'no_pdf'"
        ).rowcount
        conn.commit()
        print(f"Cleared {cleared} no-PDF entries from cache; will re-check them.\n")

    tag_vocab = load_tag_vocabulary(conn)
    print(f"Loaded {len(tag_vocab)} existing tags as vocabulary hint")
    if REINDEX_ALL:
        print("REINDEX MODE: will re-extract all papers")
    elif REINDEX_EMPTY:
        print("REINDEX-EMPTY MODE: will re-extract papers with empty fields")

    # Decide sync mode
    last_version = get_last_version(conn)
    if FULL_SYNC or REINDEX_ALL or REINDEX_EMPTY or RETRY_NO_PDF or last_version == 0:
        if last_version == 0:
            print("\nNo prior sync version recorded — doing full library fetch.")
        else:
            print("\nFull-sync mode — fetching entire Zotero library.")
        items_iter = zot.items()
    else:
        print(f"\nIncremental sync-- fetching items changed since version {last_version}.")
        items_iter = zot.items(since=last_version)

    print("Fetching from Zotero API...")
    all_items = zot.everything(items_iter)
    papers = [
        i for i in all_items
        if i["data"].get("itemType") not in ["attachment", "note"]
    ]

    # Capture the new library version BEFORE processing, so we record what we saw
    try:
        current_library_version = zot.last_modified_version()
    except Exception:
        current_library_version = None

    print(f"Got {len(papers)} papers to consider "
          f"(filtered from {len(all_items)} total items).\n")

    new_count = 0
    skipped_count = 0
    failed_count = 0
    no_pdf_count = 0

    for i, item in enumerate(papers, start=1):
        if TEST_LIMIT is not None and new_count >= TEST_LIMIT:
            print(f"\nHit TEST_LIMIT of {TEST_LIMIT}. Stopping.")
            break

        data = item["data"]
        zotero_key = data["key"]
        title = data.get("title", "")

        if already_indexed(conn, zotero_key):
            skipped_count += 1
            continue

        print(f"[{i}/{len(papers)}] {title[:75]}")

        authors = parse_authors(data.get("creators", []))
        year = safe_year(data.get("date", ""))
        venue = (data.get("publicationTitle") or
                 data.get("conferenceName") or
                 data.get("websiteTitle") or "")
        citekey = data.get("citationKey", "") or parse_citekey(data.get("extra", ""))
        abstract = data.get("abstractNote", "")

        text, source_type = get_paper_text(zotero_key)
        if not text:
            print(f"    No PDF or HTML available; caching as no_pdf.")
            mark_no_pdf(conn, zotero_key, title, authors, year, venue, citekey, abstract)
            no_pdf_count += 1
            continue
        print(f"    Source: {source_type} ({len(text)} chars)")

        try:
            print(f"    Extracting via LLM (v2 prompt)...")
            md = extract_metadata(title, authors, abstract, text, tag_vocab)
        except Exception as e:
            print(f"    LLM extraction failed: {e}")
            failed_count += 1
            continue

        conn.execute("""
            INSERT INTO papers (
                zotero_key, title, authors, year, venue, citekey, abstract,
                summary, methods, datasets, key_claims, limitations, tags,
                source_type, extracted_at, extraction_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(zotero_key) DO UPDATE SET
                title=excluded.title,
                authors=excluded.authors,
                year=excluded.year,
                venue=excluded.venue,
                citekey=excluded.citekey,
                abstract=excluded.abstract,
                summary=excluded.summary,
                methods=excluded.methods,
                datasets=excluded.datasets,
                key_claims=excluded.key_claims,
                limitations=excluded.limitations,
                tags=excluded.tags,
                source_type=excluded.source_type,
                extracted_at=excluded.extracted_at,
                extraction_version=excluded.extraction_version
        """, (
            zotero_key, title, authors, year, venue, citekey, abstract,
            md.get("summary", ""),
            json.dumps(md.get("methods", [])),
            json.dumps(md.get("datasets", [])),
            json.dumps(md.get("key_claims", [])),
            json.dumps(md.get("limitations", [])),
            json.dumps(md.get("tags", [])),
            source_type,
            datetime.now().isoformat(),
            "v2",
        ))
        conn.commit()
        new_count += 1
        print(f"    [OK] Indexed.")

        if new_count % 25 == 0:
            tag_vocab = load_tag_vocabulary(conn)

    # Record library version AFTER successful run, so next run is incremental
    if current_library_version is not None and failed_count == 0:
        set_last_version(conn, current_library_version)
        print(f"\nLibrary version recorded: {current_library_version}")
    elif failed_count > 0:
        print(f"\n{failed_count} extraction failures — not advancing library version "
              f"(those items will retry next run).")

    print(f"\n{'='*60}")
    print(f"Done. New/updated: {new_count}, skipped: {skipped_count}, "
          f"no-pdf cached: {no_pdf_count}, failed: {failed_count}")
    conn.close()

    if new_count > 0 or no_pdf_count > 0:
        sys.exit(EXIT_NEW_INDEXED if new_count > 0 else EXIT_NOTHING_NEW)
    else:
        sys.exit(EXIT_NOTHING_NEW)


if __name__ == "__main__":
    main()