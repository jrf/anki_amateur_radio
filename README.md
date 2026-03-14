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

Requires Python 3.10+, [just](https://github.com/casey/just), and [Anki](https://apps.ankiweb.net/) with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) plugin.

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
| `just update` | Download & parse latest pools from NCVEC |
| `just update-class tech` | Update a single class (`tech`, `general`, or `extra`) |
| `just build` | Build all Anki decks (requires Anki + AnkiConnect) |
| `just build-class general` | Build a single class deck |
| `just dry-run` | Show what would be downloaded |
| `just setup` | Install Python dependencies |

## How It Works

1. **`update_pools.py`** scrapes the NCVEC [question pool index](https://ncvec.org/index.php/amateur-question-pools) to auto-discover the latest pool for each license class. It downloads the `.docx` file, parses out the questions, and writes a plain-text file to each class directory. When new pool cycles are published by NCVEC, the script picks them up automatically.

2. **`build_deck.py`** reads the parsed question files and generates `.apkg` files directly using [genanki](https://github.com/kerrickstaley/genanki) — no running Anki instance needed. Each card has the question + answer choices on the front and the correct answer letter on the back, tagged by subelement (e.g. `T1A`, `G5B`, `E7D`).

## Project Structure

```
.
├── justfile                 # Task runner
├── update_pools.py          # Pool scraper & parser
├── build_deck.py            # .apkg deck builder
├── decks/                   # Generated .apkg files
├── technician/
│   └── technician_*.txt     # Parsed question pools
├── general/
│   └── general_*.txt        # Parsed question pools
└── extra/
    └── extra_*.txt          # Parsed question pools
```

## Requirements

- Python 3.10+, [mise](https://mise.jdx.dev/)
- Dependencies installed via `just setup` (uses `uv`)
