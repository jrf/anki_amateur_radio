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
import zipfile
from datetime import date
from io import BytesIO
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

# Regex to extract a figure ID like T1, T-2, G7-1, E5-1 from a filename
FIGURE_ID_IN_FILENAME_RE = re.compile(r"(?:^|[^A-Za-z])([TEG]\d+(?:-\d+)?)(?:[^A-Za-z0-9]|$)", re.IGNORECASE)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".svg"}


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


def find_pool_docx(class_key: str, pool_pages: dict[str, list[str]]) -> tuple[str | None, str | None]:
    """Try each discovered NCVEC page for a class and return (docx_url, page_url)."""
    for page_url in pool_pages.get(class_key, []):
        url = find_docx_url(page_url)
        if url:
            return url, page_url
    return None, None


def find_figure_urls(page_url: str) -> list[str]:
    """Scrape an NCVEC pool page for figure/diagram download links.

    Returns URLs for individual image files (.jpg/.png), PDFs with a
    recognizable figure ID, and .zip archives containing figures.
    """
    resp = requests.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    urls = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        lower = href.lower()
        combined = (a_tag.get_text() + " " + href).lower()
        is_figure_context = any(
            kw in combined for kw in ("diagram", "figure", "graphic", "svg")
        )
        if not is_figure_context:
            continue

        is_image = any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS)
        is_zip = lower.endswith(".zip")
        # Include PDFs that have a recognizable figure ID (e.g. G7-1.pdf)
        is_figure_pdf = lower.endswith(".pdf") and extract_figure_id(
            urllib.parse.unquote(href.split("/")[-1])
        )
        if is_image or is_zip or is_figure_pdf:
            full_url = urllib.parse.urljoin(page_url, href)
            urls.append(full_url)

    return urls


def extract_figure_id(filename: str) -> str | None:
    """Try to extract a figure ID (e.g. T1, G7-1, E5-1) from a filename."""
    m = FIGURE_ID_IN_FILENAME_RE.search(filename)
    return m.group(1).upper() if m else None


def _convert_pdf_to_png(pdf_bytes: bytes, dest: Path):
    """Convert a single-page PDF to PNG using pdftoppm (poppler).
    Falls back to saving the raw PDF if pdftoppm is not available."""
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("pdftoppm"):
        pdf_dest = dest.with_suffix(".pdf")
        pdf_dest.write_bytes(pdf_bytes)
        print(f"    (pdftoppm not found — saved as {pdf_dest.name}, "
              "install poppler to auto-convert)")
        return

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = tmp_pdf.name

    try:
        out_prefix = str(dest.with_suffix(""))
        subprocess.run(
            ["pdftoppm", "-png", "-r", "200", "-singlefile",
             tmp_pdf_path, out_prefix],
            capture_output=True, check=True,
        )
        print(f"    Converted to {dest.name}")
    except subprocess.CalledProcessError:
        pdf_dest = dest.with_suffix(".pdf")
        pdf_dest.write_bytes(pdf_bytes)
        print(f"    (pdftoppm failed — saved as {pdf_dest.name})")
    finally:
        Path(tmp_pdf_path).unlink(missing_ok=True)


def download_figures(figure_urls: list[str], figures_dir: Path) -> int:
    """Download figure images to figures_dir. Handles individual images,
    .zip archives containing SVGs, and single-figure PDFs.
    Returns count of figures saved."""
    figures_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for url in figure_urls:
        filename = urllib.parse.unquote(url.split("/")[-1])

        if filename.lower().endswith(".zip"):
            # Download and extract zip (e.g. SVG archives)
            print(f"  Downloading figure archive: {filename} ...")
            try:
                resp = requests.get(url, timeout=120)
                resp.raise_for_status()
            except requests.HTTPError as e:
                print(f"    WARNING: Failed to download {filename}: {e}")
                continue
            with zipfile.ZipFile(BytesIO(resp.content)) as zf:
                for member in zf.namelist():
                    ext = Path(member).suffix.lower()
                    if ext not in IMAGE_EXTENSIONS:
                        continue
                    fig_id = extract_figure_id(member)
                    dest_name = f"{fig_id}{ext}" if fig_id else member
                    dest = figures_dir / dest_name
                    if dest.exists():
                        print(f"    Already have: {dest_name}")
                    else:
                        dest.write_bytes(zf.read(member))
                        print(f"    Extracted: {dest_name}")
                    count += 1
            continue

        # Individual image or single-figure PDF
        fig_id = extract_figure_id(filename)
        ext = Path(filename).suffix.lower()

        # For PDFs with a figure ID, convert to PNG
        if ext == ".pdf" and fig_id:
            dest = figures_dir / f"{fig_id}.png"
            if dest.exists() or (figures_dir / f"{fig_id}.pdf").exists():
                print(f"  Already have: {fig_id}")
                count += 1
                continue
            # Skip PDF if we already have this figure as an image
            if any((figures_dir / f"{fig_id}{e}").exists()
                   for e in IMAGE_EXTENSIONS):
                count += 1
                continue

        dest_name = f"{fig_id}{ext}" if fig_id else filename
        dest = figures_dir / dest_name

        # Skip download if we already have this figure in any image format
        if fig_id and any((figures_dir / f"{fig_id}{e}").exists()
                         for e in IMAGE_EXTENSIONS):
            print(f"  Already have: {fig_id}")
            count += 1
            continue

        if dest.exists():
            print(f"  Already have: {dest_name}")
            count += 1
            continue

        print(f"  Downloading figure: {filename} -> {dest_name}")
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
        except requests.HTTPError as e:
            print(f"    WARNING: Failed ({e}), skipping")
            continue

        if ext == ".pdf" and fig_id:
            png_dest = figures_dir / f"{fig_id}.png"
            _convert_pdf_to_png(resp.content, png_dest)
        else:
            dest.write_bytes(resp.content)
        count += 1

    return count


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

    url, page_url = find_pool_docx(class_key, pool_pages)
    if not url:
        print(f"  ERROR: Could not find a .docx download for {class_name}")
        return None

    print(f"  Found: {urllib.parse.unquote(url.split('/')[-1])}")

    if dry_run:
        print("  (dry-run, skipping download & parse)")
        return None

    class_dir = REPO_ROOT / class_name
    docx_path = download_docx(url, class_dir)

    # Download figures/diagrams
    if page_url:
        figure_urls = find_figure_urls(page_url)
        if figure_urls:
            figures_dir = class_dir / "figures"
            n = download_figures(figure_urls, figures_dir)
            print(f"  {n} figure(s) in {figures_dir}")
        else:
            print("  No figure downloads found on pool page")

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
