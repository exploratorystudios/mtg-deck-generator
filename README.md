# MTG Commander Deck Generator

PySide6 desktop app for procedurally generating Magic: The Gathering Commander decks from a bundled Commander card database.

## Features

- Commander-only deck generation
- Searchable commander picker
- Archetype and strategy keyword support
- Evolutionary refinement controls
- Deck analysis for curve, roles, synergies, tribes, and color pips
- Plain-text and MTGA-style deck export

## Included Files

- `mtg_gui.py` — PySide6 desktop interface
- `deck_generator_commander.py` — Commander deck generation engine
- `deck_requirements.py` — deck structure and requirement helpers
- `data/cards_commander.json` — bundled Commander card archive

## Requirements

- Python 3.11+
- PySide6

Install dependencies:

```bash
pip install PySide6
```

## Run

From the repo root:

```bash
python3 mtg_gui.py
```

## Notes

- The app is built for Commander / EDH only.
- Generation quality and runtime depend on the selected commander, archetype, strategy keywords, candidate deck count, and evolution settings.
