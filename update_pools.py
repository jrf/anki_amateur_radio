#!/usr/bin/env python3
"""
Scrape the latest amateur radio question pools from NCVEC/ARRL,
parse the .docx files, and output text files in the format expected
by the per-class build_deck.py scripts.

Usage:
    python update_pools.py                  # download & parse all pools
    python update_pools.py --class tech     # only technician
    python update_pools.py --class general  # only general
    python update_pools.py --class extra    # only extra
    python update_pools.py --dry-run        # show what would be downloaded
"""

import argparse
import re
import urllib.parse
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from docx import Document

# ── configuration ──────────────────────────────────────────────────────────

NCVEC_INDEX_URL = "https://ncvec.org/index.php/amateur-question-pools"

# Keywords in NCVEC pool page URLs/titles that identify each license class
CLASS_URL_KEYWORDS = {
    "tech": "technician",
    "general": "general",
    "extra": "extra",
}

# Maps class key → output directory
CLASS_DIRS = {
    "tech": "technician",
    "general": "general",
    "extra": "extra",
}

# Regex for question ID lines, e.g. "T1A01 (C) [97.1]" or "T1A01 (C)"
QUESTION_ID_RE = re.compile(
    r"^([TEG]\d[A-Z]\d{2})\s+\(([A-D])\)"
)

# Regex for answer options
ANSWER_RE = re.compile(r"^([A-D])\.\s+")

REPO_ROOT = Path(__file__).resolve().parent


# ── web scraping ───────────────────────────────────────────────────────────

def find_docx_url(page_url: str) -> str | None:
    """Scrape an NCVEC pool page and return the first .docx download link
    that looks like a question pool document (not just diagrams)."""
    print(f"  Scanning {page_url} ...")
    resp = requests.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    candidates = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.lower().endswith(".docx"):
            # Skip diagram-only files
            name_lower = href.lower()
            if "diagram" in name_lower or "graphic" in name_lower or "figure" in name_lower:
                continue
            # Build absolute URL
            full_url = urllib.parse.urljoin(page_url, href)
            candidates.append(full_url)

    if not candidates:
        return None

    # Prefer the one with "Pool" or "Syllabus" in the name
    for url in candidates:
        if "pool" in url.lower() or "syllabus" in url.lower():
            return url
    return candidates[0]


def discover_pool_pages() -> dict[str, list[str]]:
    """Scrape the NCVEC question pools index page and return a dict mapping
    class key → list of pool page URLs, sorted newest first."""
    print(f"  Discovering pools from {NCVEC_INDEX_URL} ...")
    resp = requests.get(NCVEC_INDEX_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Collect all links that have a year range and a class keyword
    year_range_re = re.compile(r"(\d{4})[_-](\d{4})")
    pool_pages: dict[str, list[tuple[int, str]]] = {k: [] for k in CLASS_URL_KEYWORDS}

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        text = (a_tag.get_text() + " " + href).lower()
        m = year_range_re.search(href) or year_range_re.search(a_tag.get_text())
        if not m:
            continue
        start_year = int(m.group(1))
        for class_key, keyword in CLASS_URL_KEYWORDS.items():
            if keyword in text:
                full_url = urllib.parse.urljoin(NCVEC_INDEX_URL, href)
                pool_pages[class_key].append((start_year, full_url))
                break

    # Sort each class by start year descending (newest first) and pick the
    # pool that is currently active or the most recent one available.
    # Pool cycles start July 1, so a pool with start_year Y is active from
    # July 1 of year Y through June 30 of the end year.
    today = date.today()
    result: dict[str, list[str]] = {}
    for class_key, entries in pool_pages.items():
        entries.sort(key=lambda e: e[0], reverse=True)
        # Find the active pool: start_year where July 1 has already passed
        active = []
        for start_year, url in entries:
            effective_date = date(start_year, 7, 1)
            if effective_date <= today:
                active.append(url)
                break
        # Also include the newest pool (may be a future one for study prep)
        if entries and entries[0][1] not in active:
            active.insert(0, entries[0][1])
        result[class_key] = active if active else [url for _, url in entries]

    for class_key, urls in result.items():
        for url in urls:
            print(f"    {class_key}: {url}")

    return result


def find_pool_docx(class_key: str, pool_pages: dict[str, list[str]]) -> str | None:
    """Try each discovered NCVEC page for a class and return the first .docx URL found."""
    for page_url in pool_pages.get(class_key, []):
        url = find_docx_url(page_url)
        if url:
            return url
    return None


def download_docx(url: str, dest: Path) -> Path:
    """Download a .docx file to dest directory, return local path."""
    filename = urllib.parse.unquote(url.split("/")[-1])
    local_path = dest / filename
    if local_path.exists():
        print(f"  Already downloaded: {local_path.name}")
        return local_path
    print(f"  Downloading {filename} ...")
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    local_path.write_bytes(resp.content)
    print(f"  Saved to {local_path}")
    return local_path


# ── .docx parsing ─────────────────────────────────────────────────────────

def extract_text_from_docx(docx_path: Path) -> str:
    """Extract all paragraph text from a .docx, keeping only the question
    content (from first question ID to end).  Returns raw text ready to be
    written as a ~~-separated question file.

    Filters out section headers and subelement descriptions that appear
    between ~~ separators, keeping only actual questions."""
    doc = Document(str(docx_path))

    # Collect all non-empty paragraph text
    raw_lines = []
    started = False
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if not started:
            if QUESTION_ID_RE.match(text):
                started = True
            else:
                continue
        raw_lines.append(text)

    # Now filter: walk through ~~-delimited blocks and only keep
    # blocks that start with a valid question ID line.
    output_lines = []
    block = []
    for line in raw_lines:
        if line.strip() == "~~":
            if block and QUESTION_ID_RE.match(block[0]):
                output_lines.append("~~")
                output_lines.extend(block)
            block = []
        else:
            block.append(line)

    # Handle last block (if file doesn't end with ~~)
    if block and QUESTION_ID_RE.match(block[0]):
        output_lines.append("~~")
        output_lines.extend(block)

    # Add trailing ~~
    output_lines.append("~~")

    return "\n".join(output_lines)


def count_questions(text: str) -> int:
    """Count question IDs in the text."""
    return len(re.findall(
        r"^[TEG]\d[A-Z]\d{2}\s+\([A-D]\)",
        text,
        re.MULTILINE,
    ))


# ── output ─────────────────────────────────────────────────────────────────

def date_range_from_url(url: str) -> str:
    """Extract a date range like '2026-2030' from the URL or filename."""
    m = re.search(r"(\d{4})[_-](\d{4})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return "unknown"


def write_question_file(text: str, output_path: Path, num_questions: int):
    """Write extracted question text to file in the format expected by build_deck.py."""
    with open(output_path, "w", encoding="latin-1", errors="replace") as f:
        f.write(text)
        # Ensure trailing newline
        if not text.endswith("\n"):
            f.write("\n")
    print(f"  Wrote {num_questions} questions to {output_path}")


# ── main ───────────────────────────────────────────────────────────────────

def process_class(class_key: str, pool_pages: dict[str, list[str]], dry_run: bool = False) -> Path | None:
    """Download, parse, and write the question file for one license class."""
    class_name = CLASS_DIRS[class_key]
    print(f"\n{'='*60}")
    print(f"Processing: {class_name.upper()}")
    print(f"{'='*60}")

    url = find_pool_docx(class_key, pool_pages)
    if not url:
        print(f"  ERROR: Could not find a .docx download for {class_name}")
        return None

    print(f"  Found: {urllib.parse.unquote(url.split('/')[-1])}")

    if dry_run:
        print("  (dry-run, skipping download & parse)")
        return None

    class_dir = REPO_ROOT / class_name
    docx_path = download_docx(url, class_dir)

    text = extract_text_from_docx(docx_path)
    num_questions = count_questions(text)
    if num_questions == 0:
        print(f"  WARNING: No questions parsed from {docx_path.name}")
        print("  The .docx format may have changed. Check the file manually.")
        return None

    date_range = date_range_from_url(url)
    txt_filename = f"{class_name}_{date_range}.txt"
    txt_path = class_dir / txt_filename

    write_question_file(text, txt_path, num_questions)

    # Clean up downloaded docx
    docx_path.unlink()
    print(f"  Cleaned up {docx_path.name}")

    return txt_path


def main():
    parser = argparse.ArgumentParser(
        description="Update amateur radio question pools from NCVEC"
    )
    parser.add_argument(
        "--class", dest="license_class", choices=["tech", "general", "extra"],
        help="Only update a specific license class (default: all)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without doing it",
    )
    args = parser.parse_args()

    classes = [args.license_class] if args.license_class else ["tech", "general", "extra"]

    print("Discovering latest question pools from NCVEC...")
    pool_pages = discover_pool_pages()

    for cls in classes:
        if cls not in pool_pages or not pool_pages[cls]:
            print(f"\n  WARNING: No pool pages found for {cls} on NCVEC index.")
            print(f"  The NCVEC site structure may have changed. Check {NCVEC_INDEX_URL}")

    results = {}
    for cls in classes:
        txt_path = process_class(cls, pool_pages, dry_run=args.dry_run)
        if txt_path:
            results[cls] = txt_path

    print("\nDone!")


if __name__ == "__main__":
    main()
