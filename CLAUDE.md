# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Two-stage pipeline that scrapes official NCVEC amateur radio question pools and generates Anki flashcard decks (.apkg files) for all three U.S. license classes (Technician, General, Extra).

## Commands

All commands go through `just` (task runner). Python is invoked via `mise exec -- python`.

```sh
just              # full pipeline: update pools + build decks
just update       # scrape & parse latest pools from NCVEC
just build        # generate .apkg files from parsed pools
just dry-run      # preview what would be downloaded
just setup        # install dependencies (runs ./installdeps)
```

Single-class variants: `just update-class tech`, `just build-class general`, etc.

## Dependency Management

Uses **mise** + **uv** — never run bare `pip install`. Add packages to `requirements.txt` and run `./installdeps` (which runs `mise exec -- uv pip install -r requirements.txt`).

## Architecture

```
NCVEC website → update_pools.py → {class}/{class}_YYYY-YYYY.txt → build_deck.py → decks/{class}_class.apkg
```

**update_pools.py**: Scrapes the NCVEC index page to auto-discover pool URLs (no hardcoded years). Downloads `.docx` files, parses questions into `~~`-delimited text files. Picks the active pool based on July 1 effective dates.

**build_deck.py**: Finds the latest `*.txt` file in each class directory by lexical sort. Parses the `~~`-delimited format and generates `.apkg` files using genanki. Uses stable MD5-based IDs so deck identity is consistent across rebuilds.

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
