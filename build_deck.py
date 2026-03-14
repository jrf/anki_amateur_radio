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

# Regex to find figure references like "Figure T-1", "Figure E5-1", "Figure G7-1"
FIGURE_RE = re.compile(r"[Ff]igure\s+([A-Z]\d?-?\d+)", re.IGNORECASE)


def _normalize_figure_key(name: str) -> str:
    """Normalize a figure name to a canonical key for matching.

    Strips 'fig' prefix and collapses hyphens/underscores/spaces so that
    'Figure E5-1', 'figE5_1', and 'E5-1' all map to the same key.
    """
    key = name.lower()
    key = re.sub(r"^fig\s*", "", key)
    key = re.sub(r"[-_ ]", "", key)
    return key


def build_figure_map(figures_dir: Path) -> dict[str, Path]:
    """Build a mapping from normalized figure key → file path for all images."""
    fig_map: dict[str, Path] = {}
    if not figures_dir.is_dir():
        return fig_map
    for f in figures_dir.iterdir():
        if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
            key = _normalize_figure_key(f.stem)
            fig_map[key] = f
    return fig_map


def inject_figures(front_html: str, fig_map: dict[str, Path]) -> tuple[str, list[Path]]:
    """Find figure references in card text and append <img> tags.

    Returns the modified HTML and a list of image paths used.
    """
    used: list[Path] = []
    seen_keys: set[str] = set()
    for match in FIGURE_RE.finditer(front_html):
        ref = match.group(1)
        key = _normalize_figure_key(ref)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        if key in fig_map:
            img_path = fig_map[key]
            front_html += f'<br /><br /><img src="{img_path.name}">'
            used.append(img_path)
    return front_html, used

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

    fig_map = build_figure_map(class_dir / "figures")

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
    all_media: list[Path] = []

    for q in questions:
        front, media = inject_figures(q["front"], fig_map)
        all_media.extend(media)
        note = genanki.Note(
            model=model,
            fields=[front, q["back"]],
            tags=[q["tag"]],
        )
        deck.add_note(note)

    # Deduplicate media paths
    all_media = list(dict.fromkeys(all_media))

    DECKS_DIR.mkdir(exist_ok=True)
    output_path = DECKS_DIR / f"{deck_name}.apkg"
    pkg = genanki.Package(deck, media_files=[str(p) for p in all_media])
    pkg.write_to_file(str(output_path))
    figure_msg = f" ({len(all_media)} figures)" if all_media else ""
    print(f"  Wrote {len(questions)} cards{figure_msg} to {output_path}")
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
