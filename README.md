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

## EDHREC Suite Archive

To prefetch EDHREC suites for all commanders in your local database and build a reusable archive:

```bash
python3 scripts/prefetch_edhrec_suite.py
```

This writes:

- `cards/commander/.cache/edhrec/edhrec_commander_suite_v1.json`
- `cards/commander/.cache/edhrec/edhrec_commander_suite_v1.json.gz`

The generator will read this archive first, then fall back to per-commander cache, then optional live fetch.

## Notes

- The app is built for Commander / EDH only.
- Generation quality and runtime depend on the selected commander, archetype, strategy keywords, candidate deck count, and evolution settings.
