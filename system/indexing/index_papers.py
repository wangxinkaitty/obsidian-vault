"""
Paper indexing pipeline.

Reads papers from your Zotero library, finds attachments (PDF preferred, HTML fallback),
extracts text, sends excerpts to an LLM for structured metadata extraction,
stores results in SQLite.

Resumable: re-running skips papers already indexed.

Usage:
    python index_papers.py
"""

import os
import json
import sqlite3
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from pyzotero import zotero
from pypdf import PdfReader
from bs4 import BeautifulSoup
from openai import OpenAI

# ─── Config ─────────────────────────────────────────────────────────
load_dotenv()

DB_PATH = "papers.db"
TEST_LIMIT = 3              # First run: only index this many new papers. Set to None for unlimited.
MAX_PDF_PAGES = 25          # Max PDF pages to read per paper
MAX_TEXT_CHARS = 12000      # Max chars of text to send to LLM (cost control)

ZOTERO_DATA_DIR = os.path.expanduser("~/Zotero")

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
    conn.commit()
    return conn


def already_indexed(conn, zotero_key):
    cursor = conn.execute("SELECT 1 FROM papers WHERE zotero_key = ?", (zotero_key,))
    return cursor.fetchone() is not None


# ─── Attachment file resolution ─────────────────────────────────────
def get_attachment_path(attachment_data):
    """Return path to the attachment file: local first, temp download fallback. None if unavailable."""
    attachment_key = attachment_data.get("key")
    filename = attachment_data.get("filename")

    # Try local file first
    if attachment_key and filename:
        local_path = os.path.join(ZOTERO_DATA_DIR, "storage", attachment_key, filename)
        if os.path.exists(local_path):
            return local_path, None  # (path, tmp_to_cleanup)

    # Fall back to API
    if not attachment_key:
        return None, None
    try:
        file_bytes = zot.file(attachment_key)
    except Exception as e:
        print(f"    Couldn't get attachment locally or from API: {e}")
        return None, None

    suffix = os.path.splitext(filename or "")[1] or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        return tmp.name, tmp.name


# ─── Text extraction ────────────────────────────────────────────────
def extract_pdf_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        text_parts = []
        total_chars = 0
        for page in reader.pages[:MAX_PDF_PAGES]:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
            total_chars += len(page_text)
            if total_chars >= MAX_TEXT_CHARS:
                break
        return "\n".join(text_parts)[:MAX_TEXT_CHARS]
    except Exception as e:
        print(f"    PDF parsing failed: {e}")
        return None


def extract_html_text(html_path):
    try:
        with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        soup = BeautifulSoup(html, "html.parser")
        # Strip nav/scripts/styles to reduce noise
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)[:MAX_TEXT_CHARS]
    except Exception as e:
        print(f"    HTML parsing failed: {e}")
        return None


def get_paper_text(item_key):
    """Find best available attachment (PDF first, then HTML), extract text. Returns (text, source_type)."""
    children = zot.children(item_key)

    pdf_attachments = [c for c in children if c["data"].get("contentType") == "application/pdf"]
    html_attachments = [c for c in children if c["data"].get("contentType") in ("text/html", "application/xhtml+xml")]

    # Prefer PDF
    if pdf_attachments:
        path, tmp = get_attachment_path(pdf_attachments[0]["data"])
        if path:
            try:
                text = extract_pdf_text(path)
                if text and text.strip():
                    return text, "pdf"
            finally:
                if tmp:
                    try: os.unlink(tmp)
                    except Exception: pass

    # Fall back to HTML
    if html_attachments:
        path, tmp = get_attachment_path(html_attachments[0]["data"])
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
EXTRACTION_PROMPT = """You are a research assistant extracting structured information from academic papers and articles.

Given a document, return ONLY a valid JSON object (no markdown, no commentary) with these fields:

- methods: list of methods/techniques used or discussed (e.g., "reinforcement learning", "transformers", "Bayesian inference"). 1-6 entries. Empty list if not applicable.
- datasets: list of datasets used or analyzed (or empty list if none). Be specific (e.g., "ImageNet", "Atari ALE"), not generic.
- key_claims: list of 2-4 main claims or findings, each a single concise sentence in your own words.
- limitations: list of limitations or future work items mentioned (or empty list if none).
- tags: list of 3-7 short topic tags in lowercase-hyphenated style (e.g., "reinforcement-learning", "memory").

Title: {title}
Authors: {authors}
Abstract: {abstract}

Document text (excerpt, may be truncated):
{text}
"""


def extract_metadata(title, authors, abstract, text):
    response = llm.chat.completions.create(
        model="deepseek-chat",
        messages=[{
            "role": "user",
            "content": EXTRACTION_PROMPT.format(
                title=title or "[unknown]",
                authors=authors or "[unknown]",
                abstract=abstract or "[no abstract]",
                text=text,
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


# ─── Main loop ──────────────────────────────────────────────────────
def main():
    conn = init_db()

    print("Fetching all items from Zotero...")
    all_items = zot.everything(zot.items())
    papers = [
        i for i in all_items
        if i["data"].get("itemType") not in ["attachment", "note"]
    ]
    print(f"Library has {len(papers)} papers (excluding attachments/notes).\n")

    new_count = 0
    skipped_count = 0
    failed_count = 0

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
        venue = data.get("publicationTitle") or data.get("conferenceName") or data.get("websiteTitle") or ""
        citekey = data.get("citationKey", "") or parse_citekey(data.get("extra", ""))
        abstract = data.get("abstractNote", "")

        text, source_type = get_paper_text(zotero_key)
        if not text:
            print(f"    No PDF or HTML available; skipping.")
            failed_count += 1
            continue
        print(f"    Source: {source_type}")

        try:
            print(f"    Extracting metadata via LLM...")
            metadata = extract_metadata(title, authors, abstract, text)
        except Exception as e:
            print(f"    LLM extraction failed: {e}")
            failed_count += 1
            continue

        conn.execute("""
            INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            zotero_key, title, authors, year, venue, citekey, abstract,
            json.dumps(metadata.get("methods", [])),
            json.dumps(metadata.get("datasets", [])),
            json.dumps(metadata.get("key_claims", [])),
            json.dumps(metadata.get("limitations", [])),
            json.dumps(metadata.get("tags", [])),
            source_type,
            datetime.now().isoformat(),
        ))
        conn.commit()
        new_count += 1
        print(f"    ✓ Indexed.")

    print(f"\n{'='*60}")
    print(f"Done. New: {new_count}, already indexed: {skipped_count}, failed: {failed_count}")
    conn.close()


if __name__ == "__main__":
    main()