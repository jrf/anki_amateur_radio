# Anki Decks for Amateur Radio Exams

Automatically generated [Anki](https://apps.ankiweb.net/) flashcard decks for all three U.S. amateur radio license classes, built from the official [NCVEC](https://ncvec.org) question pools.

## Pre-built Decks

Ready-to-import `.apkg` files are in the `decks/` directory:

| Deck | Pool Cycle |
|---|---|
| `technician_class.apkg` | 2026-2030 |
| `general_class.apkg` | 2023-2027 |
| `extra_class.apkg` | 2024-2028 |

Import any of these directly into Anki via **File > Import**.

## Quick Start

Requires [mise](https://mise.jdx.dev/) and [just](https://github.com/casey/just).

```sh
# Install Python dependencies
just setup

# Preview what would be downloaded
just dry-run

# Download latest question pools and build decks
just
```

## Commands

| Command | Description |
|---|---|
| `just` | Update pools + build all decks |
| `just update` | Download & parse latest pools + figures from NCVEC |
| `just update-class tech` | Update a single class (`tech`, `general`, or `extra`) |
| `just build` | Build all `.apkg` decks to `decks/` |
| `just build-class general` | Build a single class deck |
| `just dry-run` | Show what would be downloaded |
| `just setup` | Install Python dependencies |

## How It Works

1. **`update_pools.py`** scrapes the NCVEC [question pool index](https://ncvec.org/index.php/amateur-question-pools) to auto-discover the latest pool for each license class. It downloads the `.docx` file, parses out the questions, and writes a plain-text file to each class directory. It also downloads all associated diagrams and figures — individual images (Technician), SVG archives (Extra), and single-figure PDFs converted to PNG (General). When new pool cycles are published by NCVEC, the script picks them up automatically.

2. **`build_deck.py`** reads the parsed question files and generates `.apkg` files directly using [genanki](https://github.com/kerrickstaley/genanki) — no running Anki instance needed. Each card has the question + answer choices on the front and the correct answer letter on the back, tagged by subelement (e.g. `T1A`, `G5B`, `E7D`). Questions that reference figures (circuit diagrams, Smith charts, schematic symbols, antenna patterns) automatically include the corresponding image on the card.

## Project Structure

```
.
├── justfile                 # Task runner
├── update_pools.py          # Pool scraper & parser
├── build_deck.py            # .apkg deck builder
├── decks/                   # Generated .apkg files
├── technician/
│   ├── technician_*.txt     # Parsed question pools
│   └── figures/             # T1.jpg, T2.jpg, T3.jpg
├── general/
│   ├── general_*.txt        # Parsed question pools
│   └── figures/             # G7-1.png
└── extra/
    ├── extra_*.txt          # Parsed question pools
    └── figures/             # E5-1.svg, E6-1.svg, ... E9-3.svg
```

## Requirements

- Python 3.10+, [mise](https://mise.jdx.dev/)
- Dependencies installed via `just setup` (uses `uv`)
- Optional: `pdftoppm` (from [poppler](https://poppler.freedesktop.org/)) for converting figure PDFs to PNG
