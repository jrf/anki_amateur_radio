# Amateur Radio Anki Deck Builder

python := "mise exec -- python"

# Update pools and build .apkg decks
all: update build

# Download and parse the latest question pools from NCVEC
update:
    {{python}} update_pools.py

# Update a single class: just update-class tech|general|extra
update-class class:
    {{python}} update_pools.py --class {{class}}

# Build all .apkg decks to decks/
build:
    {{python}} build_deck.py

# Build a single class deck
build-class class:
    {{python}} build_deck.py --class {{class}}

# Show what would be downloaded without doing it
dry-run:
    {{python}} update_pools.py --dry-run

# Install Python dependencies
setup:
    ./installdeps
