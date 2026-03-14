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
    python update_pools.py --build          # also run build_deck.py after
    python update_pools.py --dry-run        # show what would be downloaded
"""

import argparse
import os
import re
import sys
import urllib.parse
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from docx import Document

# ── configuration ──────────────────────────────────────────────────────────

NCVEC_POOL_PAGES = {
    "tech": [
        "https://ncvec.org/index.php/2026-2030-technician-question-pool",
        "https://ncvec.org/index.php/2022-2026-technician-question-pool",
    ],
    "general": [
        "https://ncvec.org/index.php/2023-2027-general-question-pool-release",
    ],
    "extra": [
        "https://ncvec.org/index.php/2024-2028-extra-class-question-pool-release",
    ],
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


def find_pool_docx(class_key: str) -> str | None:
    """Try each NCVEC page for a class and return the first .docx URL found."""
    for page_url in NCVEC_POOL_PAGES[class_key]:
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


def update_build_script(class_dir: Path, txt_filename: str):
    """Update the build_deck.py in class_dir to reference the new txt file."""
    build_script = class_dir / "build_deck.py"
    if not build_script.exists():
        return

    content = build_script.read_text()
    # Find the fname = '...' line and update it
    new_content = re.sub(
        r"(fname\s*=\s*['\"])\./.+?(\.txt['\"])",
        rf"\g<1>./{txt_filename}\g<2>",
        content,
    )
    if new_content != content:
        build_script.write_text(new_content)
        print(f"  Updated {build_script} to use {txt_filename}")


# ── main ───────────────────────────────────────────────────────────────────

def process_class(class_key: str, dry_run: bool = False) -> Path | None:
    """Download, parse, and write the question file for one license class."""
    class_name = CLASS_DIRS[class_key]
    print(f"\n{'='*60}")
    print(f"Processing: {class_name.upper()}")
    print(f"{'='*60}")

    url = find_pool_docx(class_key)
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
    update_build_script(class_dir, txt_filename)

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
        "--build", action="store_true",
        help="Run build_deck.py after updating (requires Anki + AnkiConnect)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be downloaded without doing it",
    )
    args = parser.parse_args()

    classes = [args.license_class] if args.license_class else ["tech", "general", "extra"]

    results = {}
    for cls in classes:
        txt_path = process_class(cls, dry_run=args.dry_run)
        if txt_path:
            results[cls] = txt_path

    if args.build and results:
        print(f"\n{'='*60}")
        print("Building Anki decks...")
        print(f"{'='*60}")
        print("NOTE: Anki must be running with AnkiConnect plugin installed.")
        for cls, txt_path in results.items():
            build_script = txt_path.parent / "build_deck.py"
            if build_script.exists():
                print(f"\n  Running {build_script} ...")
                os.system(f"cd {txt_path.parent} && python build_deck.py")

    print("\nDone!")


if __name__ == "__main__":
    main()
