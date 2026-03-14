# Amateur Radio Anki Deck Builder

# Update pools, build decks, and export .apkg files
all: build

# Download and parse the latest question pools from NCVEC
update:
    python update_pools.py

# Update a single class: just update-class tech|general|extra
update-class class:
    python update_pools.py --class {{class}}

# Build all Anki decks (requires Anki running with AnkiConnect)
build:
    python update_pools.py --build

# Build a single class deck
build-class class:
    cd {{class}} && python build_deck.py

# Show what would be downloaded without doing it
dry-run:
    python update_pools.py --dry-run

# Install Python dependencies
setup:
    pip install requests beautifulsoup4 python-docx
