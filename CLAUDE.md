# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Two-stage pipeline that scrapes official NCVEC amateur radio question pools and generates Anki flashcard decks (.apkg files) for all three U.S. license classes (Technician, General, Extra).

## Commands

All commands go through `just` (task runner). Python is invoked via `mise exec -- python`.

```sh
just              # full pipeline: update pools + build decks
just update       # scrape & parse latest pools + download figures from NCVEC
just build        # generate .apkg files from parsed pools
just dry-run      # preview what would be downloaded
just setup        # install dependencies (runs ./installdeps)
```

Single-class variants: `just update-class tech`, `just build-class general`, etc.

## Dependency Management

Uses **mise** + **uv** — never run bare `pip install`. Add packages to `requirements.txt` and run `./installdeps` (which runs `mise exec -- uv pip install -r requirements.txt`).

System dependency: `pdftoppm` (from poppler) is used to convert single-figure PDFs to PNG. If missing, PDFs are saved as-is with a warning.

## Architecture

```
NCVEC website → update_pools.py → {class}/{class}_YYYY-YYYY.txt   → build_deck.py → decks/{class}_class.apkg
                                → {class}/figures/{id}.{jpg,svg,png}  ↗ (embedded as media)
```

**update_pools.py** (scraper):
- Scrapes the NCVEC index page to auto-discover pool page URLs (no hardcoded years). Picks the active pool based on July 1 effective dates.
- Downloads `.docx` files, parses questions into `~~`-delimited text files, then deletes the `.docx`.
- Also scrapes pool pages for figure/diagram links: downloads individual images (Tech JPGs), extracts SVG zips (Extra), and converts single-figure PDFs to PNG via `pdftoppm` (General). Saves to `{class}/figures/` with figure IDs extracted from filenames (e.g. `T1.jpg`, `E5-1.svg`, `G7-1.png`).

**build_deck.py** (deck builder):
- Finds the latest `*.txt` file in each class directory by lexical sort.
- Parses the `~~`-delimited format and generates `.apkg` files using genanki.
- Uses stable MD5-based IDs so deck identity is consistent across rebuilds.
- Scans `{class}/figures/` for images, matches "Figure X-Y" references in question text to files via normalized keys (stripping `fig` prefix, collapsing hyphens/underscores), injects `<img>` tags, and bundles media into the `.apkg` package.

## Question File Format

```
~~
T1A01 (C) [97.1]
What is the question text?
A. Option A
B. Option B
C. Option C
D. Option D
~~
```

The header line contains: question ID, correct answer letter in parens, optional CFR reference in brackets. The first 3 characters of the ID (e.g. `T1A`) are used as the Anki card tag.

## Figure Handling

Figure names vary across NCVEC sources. The matching system normalizes both question references ("Figure E5-1") and filenames ("figE5_1.png", "E5-1.svg") to a canonical key by lowercasing, stripping `fig` prefix, and removing hyphens/underscores/spaces. To add a new figure, drop an image file into the appropriate `{class}/figures/` directory with the figure ID somewhere in the filename.
