#!/usr/bin/env python3
"""
Build Anki .apkg decks from parsed question pool text files.

Usage:
    python build_deck.py                  # build all classes
    python build_deck.py --class tech     # build one class
"""

import argparse
import hashlib
import re
from pathlib import Path

import genanki

REPO_ROOT = Path(__file__).resolve().parent
DECKS_DIR = REPO_ROOT / "decks"

# Class configs: key → (directory name, deck name, model_id, deck_id)
# model_id and deck_id must be stable integers for genanki (generated from names)
CLASSES = {
    "tech": ("technician", "technician_class"),
    "general": ("general", "general_class"),
    "extra": ("extra", "extra_class"),
}


def stable_id(name: str) -> int:
    """Generate a stable integer ID from a string, for genanki."""
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def find_latest_pool_file(class_dir: Path) -> Path | None:
    """Find the most recent question pool .txt file in a class directory."""
    txt_files = sorted(
        [f for f in class_dir.glob("*.txt") if f.name != "prompt.txt"],
        key=lambda f: f.name,
        reverse=True,
    )
    return txt_files[0] if txt_files else None


def parse_questions(txt_path: Path) -> list[dict]:
    """Parse a ~~-delimited question pool file into a list of question dicts."""
    text = txt_path.read_text(encoding="latin-1").splitlines()
    text = [line for line in text if line.strip()]
    indices = [i for i, line in enumerate(text) if "~~" in line]

    questions = []
    for idx in range(len(indices) - 1):
        start = indices[idx]
        end = indices[idx + 1]
        block = text[start + 1 : end]
        if not block:
            continue
        try:
            header = block[0]
            tag = header[:3]
            answer = header.split(" ")[1][1]
            body_lines = block[1:]
            questions.append({
                "tag": tag,
                "answer": answer,
                "front": "<br /><br />".join(body_lines),
                "back": answer,
            })
        except (IndexError, KeyError):
            continue

    return questions


def build_apkg(class_key: str) -> Path | None:
    """Build a .apkg file for a license class. Returns output path or None."""
    dir_name, deck_name = CLASSES[class_key]
    class_dir = REPO_ROOT / dir_name

    txt_path = find_latest_pool_file(class_dir)
    if not txt_path:
        print(f"  No question pool file found in {class_dir}")
        return None

    print(f"  Parsing {txt_path.name} ...")
    questions = parse_questions(txt_path)
    if not questions:
        print(f"  WARNING: No questions parsed from {txt_path.name}")
        return None

    model = genanki.Model(
        stable_id(f"{deck_name}_model"),
        f"{deck_name} Model",
        fields=[{"name": "Front"}, {"name": "Back"}],
        templates=[{
            "name": "Card 1",
            "qfmt": "{{Front}}",
            "afmt": '{{FrontSide}}<hr id="answer">{{Back}}',
        }],
    )

    deck = genanki.Deck(stable_id(deck_name), deck_name)

    for q in questions:
        note = genanki.Note(
            model=model,
            fields=[q["front"], q["back"]],
            tags=[q["tag"]],
        )
        deck.add_note(note)

    DECKS_DIR.mkdir(exist_ok=True)
    output_path = DECKS_DIR / f"{deck_name}.apkg"
    genanki.Package(deck).write_to_file(str(output_path))
    print(f"  Wrote {len(questions)} cards to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build Anki .apkg decks")
    parser.add_argument(
        "--class", dest="license_class", choices=["tech", "general", "extra"],
        help="Only build a specific license class (default: all)",
    )
    args = parser.parse_args()

    classes = [args.license_class] if args.license_class else ["tech", "general", "extra"]

    for cls in classes:
        dir_name, deck_name = CLASSES[cls]
        print(f"\n{'='*60}")
        print(f"Building: {deck_name}")
        print(f"{'='*60}")
        build_apkg(cls)

    print("\nDone!")


if __name__ == "__main__":
    main()
