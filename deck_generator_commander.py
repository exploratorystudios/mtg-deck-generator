#!/usr/bin/env python3
"""
MTG Commander Deck Generator

Generates 100-card Commander decks (99 + commander) using rigorous MTG theory:
  - Singleton constraint — one copy of each nonbasic card
  - Commander-driven color identity and auto-detected strategy hints
  - Frank Karsten's hypergeometric mana base mathematics
  - Archetype-specific mana curve targets and role ratios (commander-tuned)
  - Pairwise synergy graph scoring (tribal, ETB, GY, tokens, etc.)
  - Constraint-greedy card selection with evolutionary refinement

Usage:
  python deck_generator_commander.py --list-commanders
  python deck_generator_commander.py --commander "Krenko, Mob Boss" --archetype aggro
  python deck_generator_commander.py --commander "Atraxa, Praetors' Voice" --archetype midrange
  python deck_generator_commander.py --commander "Teferi, Hero of Dominaria" --archetype control
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter, defaultdict

from deck_requirements import (
    CREATURE_TYPES,
    build_deck_state,
    commander_role_penalty,
    deck_requirement_penalty,
    evaluate_card_requirements,
)

CARDS_DIR = os.path.join(os.path.dirname(__file__), "cards", "commander")
COMMANDER_DECK_SIZE = 100   # total including commander
COMMANDER_MAIN_SIZE = 99    # cards in the 99 (not commander)
_GOLDFISH_CACHE: dict[tuple, dict[str, float]] = {}
_NUMBER_WORD_RE = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|\w+)"


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY KEYWORD → ORACLE TEXT EXPANSION
# Many strategy terms are colloquial and don't appear verbatim in oracle text.
# Each entry maps a keyword to one or more regex patterns that actually appear
# on relevant cards. Patterns are OR'd: a card matches if ANY pattern hits.
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_ORACLE_ALIASES: dict[str, list[str]] = {
    # Colloquial mechanics → oracle text
    "burn":        [r"deals? \d+ damage", r"damage to any target", r"damage to target (creature|player|planeswalker)"],
    "damage":      [r"deals? \d+ damage", r"damage to any target", r"deals? damage to each", r"whenever .{0,30}deals damage"],
    "ramp":        [
        r"search your library for (?:up to \w+ )?(?:a )?(?:basic )?land",
        r"search your library for a (?:plains|island|swamp|forest|mountain)\b",
        r"put (a|that) land (card )?onto the battlefield",
        r"adds? \{[WUBRGC0-9]\}",         # any single mana pip (colored or colorless)
        r"adds? mana (of|in) (any|your)",  # e.g. Arcane Signet, Fellwar Stone
        r"add (one|\d+|x) mana of any color",
    ],
    "draw":        [r"draw (a|two|three|four|\w+) cards?", r"scry \d+", r"surveil \d+"],
    "tutor":       [r"search your library for (?:a|an) (?:card|creature|artifact|enchantment|instant|sorcery)", r"search your library for a card"],
    "lifegain":    [r"you gain \d+ life", r"gain \d+ life", r"whenever you gain life"],
    "drain":       [r"each opponent loses \d+ life", r"target opponent loses \d+ life", r"whenever .{0,30}loses life", r"you gain life and each opponent loses life"],
    "reanimator":  [r"return target .* card from (a|your) graveyard", r"put .* from (a|your) graveyard (onto|into) the battlefield"],
    "reanimation": [r"return target .* card from (a|your) graveyard", r"put .* from (a|your) graveyard (onto|into) the battlefield"],
    "recursion":   [r"return (target |a |each )?.* from (a|your|their) graveyard", r"from the graveyard to (the|your) hand"],
    "etb":         [r"when(ever)? .{0,40} enters( the battlefield)?", r"enters with"],
    "blink":       [r"exile .{0,40}(then return|return it)", r"return it to the battlefield", r"flicker"],
    "flicker":     [r"exile .{0,40}(then return|return it)", r"return it to the battlefield", r"flicker"],
    "looting":     [r"draw (a|\d+) card.{0,30}discard", r"discard .{0,30}draw (a|\d+) card"],
    "theft":       [r"gain control of", r"you control .{0,20}opponent", r"exchange control"],
    "tempo":       [r"return .{0,40} to (its owner|your hand|their owner)", r"counter target (spell|ability)", r"tapped and doesn.t untap"],
    "infinite":    [r"untap .{0,30}(add|mana)", r"take an extra (turn|step)", r"create \d+ cop"],
    "tokens":      [r"create (a|an|\d+) .{0,30}token", r"token creature", r"creature token"],
    "graveyard":   [r"graveyard"],
    "sacrifice":   [r"sacrifice (a|an|target|\{0,20})", r"when .{0,60} dies", r"when .{0,60} is put into"],
    "death_trigger":[r"when(?:ever)? .{0,60} dies", r"dies,? ", r"whenever .{0,60}is put into a graveyard"],
    "bounce":      [r"return target .{0,30} to (its owner.s hand|your hand|their hand)"],
    "counter":     [r"counter target (spell|ability|creature spell|noncreature spell)"],
    "removal":     [r"destroy target", r"exile target", r"target creature gets? -\d+/-\d+", r"deals? \d+ damage to target"],
    "interaction": [r"counter target", r"destroy target", r"exile target", r"return target .{0,30} to (its owner.s hand|your hand|their hand)", r"target player discards?"],
    "counters":    [r"\+1/\+1 counter", r"-1/-1 counter", r"place .{0,20} counter", r"with \d+ (additional )?\+1/\+1"],
    "proliferate": [r"proliferate"],
    "mill":        [rf"mill {_NUMBER_WORD_RE} cards?", r"mills? cards?", r"put the top .{0,30}card.{0,20}into .{0,20}graveyard", r"library into .{0,10}graveyard"],
    "discard":     [r"discard"],
    "copy":        [r"copy (of |a |target )", r"copies of", r"create a (token that is a )?copy"],
    "equipment":   [r"equip \{", r"equipment", r"equipped creature"],
    "auras":       [r"enchant creature", r"aura spell", r"enchanted creature"],
    "evasion":     [r"flying", r"menace", r"can't be blocked", r"skulk", r"shadow", r"horsemanship", r"intimidate", r"fear", r"trample"],
    "protection":  [r"hexproof", r"ward", r"shroud", r"indestructible", r"protection from"],
    "lords":       [r"other .{0,20}creatures? you control get \+", r"creatures? of the chosen type get \+", r"other elves? you control get \+"],
    "stax":        [r"can.t cast more than", r"spells? cost \{?\d+\}? more", r"players can.t", r"skip (their|your) untap", r"lands don.t untap", r"sacrifice (?:a|an) land"],
    "group_slug":  [r"each player loses \d+ life", r"each opponent loses \d+ life", r"whenever a player casts", r"at the beginning of each upkeep", r"each player sacrifices"],
    "voltron_enabler": [r"equip \{", r"enchant creature", r"equipped creature gets \+", r"enchanted creature gets \+"],
    "keyword_grant": [r"creatures you control (gain|have|get)", r"enchanted creature has", r"equipped creature has"],
    "spells":      [r"whenever you cast (a|an|your) (instant|sorcery|noncreature|spell)",
                    r"prowess", r"magecraft"],
    "stickers":    [r"sticker", r"ticket"],
}

STRATEGY_TYPE_ALIASES: dict[str, str] = {
    "spells":       r"\b(Instant|Sorcery)\b",
    "instants":     r"\bInstant\b",
    "sorceries":    r"\bSorcery\b",
    "storm":        r"\b(Instant|Sorcery)\b",
    "prowess":      r"\b(Instant|Sorcery)\b",
    "creatures":    r"\bCreature\b",
    "planeswalkers":r"\bPlaneswalker\b",
    "artifacts":    r"\bArtifact\b",
    "enchantments": r"\bEnchantment\b",
    "equipment":    r"\bEquipment\b",
    "auras":        r"\bAura\b",
    "vehicles":     r"\bVehicle\b",
}

STRATEGY_PHRASE_ALIASES: dict[str, str] = {
    "go wide": "go_wide",
    "go-wide": "go_wide",
    "group slug": "group_slug",
    "group-slug": "group_slug",
    "card advantage": "card_advantage",
    "mana advantage": "mana_advantage",
    "tempo advantage": "tempo_advantage",
}

STRATEGY_KEYWORD_EXPANSIONS: dict[str, list[str]] = {
    "go_wide": ["tokens", "anthem"],
    "aristocrats": ["sacrifice", "death_trigger", "drain"],
    "voltron": ["equipment", "auras", "voltron_enabler", "keyword_grant"],
    "tempo": ["tempo", "evasion", "interaction"],
    "stax": ["stax", "interaction"],
    "group_slug": ["group_slug", "drain", "damage"],
    "interaction": ["removal", "counter", "bounce", "discard"],
    "protection": ["protection", "hexproof", "ward"],
    "card_advantage": ["draw", "tutor"],
    "mana_advantage": ["ramp"],
    "tempo_advantage": ["tempo", "evasion"],
    "equipment": ["equipment", "voltron_enabler"],
    "auras": ["auras", "voltron_enabler"],
    "lords": ["lords", "anthem", "tribal"],
}

# ─────────────────────────────────────────────────────────────────────────────
# ARCHETYPE CONFIGURATION
# Based on competitive practice: Reid Duke "Level One" series, Frank Karsten
# articles, and simulation-derived curve targets.
# ─────────────────────────────────────────────────────────────────────────────

# Commander archetype configs tuned for 99-card singleton:
#   • Higher land counts (36-38) — singleton needs more consistency
#   • Strong ramp ratios — commander tax and long game require acceleration
#   • Strong draw ratios — can't rely on 4-ofs, card advantage is critical
#   • Broader curves — 99 slots allow wider threat distribution
#   • Curve target sums = COMMANDER_MAIN_SIZE - land_count
ARCHETYPE_CONFIG = {
    "aggro": {
        "land_count": 33,
        "avg_cmc_baseline": 2.0,
        "max_cmc": 5,
        # Nonland slots: 99 - 33 = 66
        "curve_targets": {0: 4, 1: 18, 2: 18, 3: 14, 4: 8, 5: 3, 6: 1},
        "role_ratios": {
            "threat":      0.48,
            "removal":     0.16,
            "counterspell":0.00,
            "draw":        0.12,
            "disruption":  0.03,
            "ramp":        0.11,
            "tutor":       0.01,
            "utility":     0.09,
        },
    },
    "midrange": {
        "land_count": 36,
        "avg_cmc_baseline": 2.75,
        "max_cmc": 8,
        # Nonland slots: 99 - 36 = 63
        "curve_targets": {0: 2, 1: 8, 2: 14, 3: 16, 4: 12, 5: 8, 6: 3},
        "role_ratios": {
            "threat":      0.30,
            "removal":     0.18,
            "counterspell":0.03,
            "draw":        0.18,
            "disruption":  0.05,
            "ramp":        0.15,
            "tutor":       0.05,
            "utility":     0.06,
        },
    },
    "control": {
        "land_count": 38,
        "avg_cmc_baseline": 3.0,
        "max_cmc": 10,
        # Nonland slots: 99 - 38 = 61
        "curve_targets": {0: 2, 1: 6, 2: 12, 3: 12, 4: 10, 5: 8, 6: 11},
        "role_ratios": {
            "threat":      0.10,
            "removal":     0.20,
            "counterspell":0.22,
            "draw":        0.25,
            "disruption":  0.03,
            "ramp":        0.12,
            "tutor":       0.03,
            "utility":     0.05,
        },
    },
    "combo": {
        "land_count": 33,
        "avg_cmc_baseline": 2.5,
        "max_cmc": 9,
        # Nonland slots: 99 - 33 = 66
        "curve_targets": {0: 4, 1: 10, 2: 16, 3: 16, 4: 10, 5: 6, 6: 4},
        "role_ratios": {
            "threat":      0.15,
            "removal":     0.06,
            "counterspell":0.08,
            "draw":        0.25,
            "disruption":  0.04,
            "ramp":        0.20,
            "tutor":       0.16,
            "utility":     0.06,
        },
    },
}

# Role clusters used to turn archetype fit into a deck-aware signal.
# Cards should score better when they reinforce the role pattern the deck is
# already converging toward, not just when they are generically legal for the
# archetype in isolation.
ARCHETYPE_ROLE_CLUSTERS: dict[str, tuple[tuple[str, frozenset[str]], ...]] = {
    "aggro": (
        ("pressure", frozenset({"threat", "wincon"})),
        ("tempo", frozenset({"removal", "disruption"})),
        ("velocity", frozenset({"draw", "ramp"})),
    ),
    "midrange": (
        ("value", frozenset({"threat", "draw", "utility", "wincon"})),
        ("interaction", frozenset({"removal", "disruption"})),
        ("mana", frozenset({"ramp", "tutor"})),
    ),
    "control": (
        ("interaction", frozenset({"counterspell", "removal", "sweeper", "disruption"})),
        ("advantage", frozenset({"draw", "tutor", "utility"})),
        ("finishers", frozenset({"threat", "wincon"})),
    ),
    "combo": (
        ("engine", frozenset({"draw", "tutor", "ramp", "utility"})),
        ("protection", frozenset({"counterspell", "disruption", "removal"})),
        ("payload", frozenset({"wincon", "threat"})),
    ),
}

# Karsten source requirements: {pip_count: {turn: sources_needed}}
# Scaled for a 24-land deck at ~90% consistency threshold.
# Source: Frank Karsten, ChannelFireball / TCGPlayer 2022 update.
KARSTEN_SOURCES = {
    1: {1: 14, 2: 13, 3: 12, 4: 11},
    2: {2: 20, 3: 18, 4: 17},
    3: {3: 23, 4: 22},
}


# ─────────────────────────────────────────────────────────────────────────────
# CARD DATABASE LOADING
# ─────────────────────────────────────────────────────────────────────────────

def extract_strategy_terms(strategy_text: str) -> list[str]:
    """Normalize user-facing strategy text into internal keyword tokens."""
    text = (strategy_text or "").lower().strip()
    if not text:
        return []
    for phrase, replacement in STRATEGY_PHRASE_ALIASES.items():
        text = text.replace(phrase, replacement)
    return [tok for tok in re.split(r"[,\s]+", text) if tok]


_TRIBE_TOKEN_OVERRIDES: dict[str, str] = {
    "elves": "elf",
    "faeries": "faerie",
    "wolves": "wolf",
}
_NON_TRIBE_STRATEGY_TOKENS: frozenset[str] = frozenset(
    {
        "tribal", "tribes", "aggro", "midrange", "control", "combo", "tempo",
        "ramp", "draw", "removal", "interaction", "spells", "spell", "tokens",
        "graveyard", "artifact", "artifacts", "enchantment", "enchantments",
        "voltron", "storm", "stax", "lifegain", "drain", "burn",
    }
    | set(STRATEGY_ORACLE_ALIASES.keys())
    | set(STRATEGY_TYPE_ALIASES.keys())
    | set(STRATEGY_KEYWORD_EXPANSIONS.keys())
)


def _strategy_token_to_tribe(token: str) -> str | None:
    tok = (token or "").strip().lower()
    if not tok:
        return None
    if tok in CREATURE_TYPES:
        return tok
    mapped = _TRIBE_TOKEN_OVERRIDES.get(tok)
    if mapped and mapped in CREATURE_TYPES:
        return mapped
    if tok.endswith("s") and tok[:-1] in CREATURE_TYPES:
        return tok[:-1]
    # Fallback for tribes not in the curated CREATURE_TYPES subset (e.g. Centaur):
    # accept a plain alphabetic token that is not a known strategy term.
    if tok.isalpha() and len(tok) >= 3 and tok not in _NON_TRIBE_STRATEGY_TOKENS:
        singular = tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok
        if singular not in _NON_TRIBE_STRATEGY_TOKENS:
            return singular
    return None


def apply_strategy_tribal_mode(
    plan_profile: dict[str, object] | None,
    strategy_text: str,
) -> dict[str, object]:
    """
    If user strategy includes 'tribal'/'tribes' + a recognized creature type,
    enable normal tribal plan steering (not strict tribal filtering).
    """
    terms = extract_strategy_terms(strategy_text)
    if not terms:
        return dict(plan_profile or {})
    if not any(t in {"tribal", "tribes"} for t in terms):
        return dict(plan_profile or {})

    strategy_tribe: str | None = None
    for tok in terms:
        tribe = _strategy_token_to_tribe(tok)
        if tribe:
            strategy_tribe = tribe
            break
    if not strategy_tribe:
        return dict(plan_profile or {})

    profile = dict(plan_profile or {})
    plans = set(profile.get("plans", frozenset()))
    plans.add("tribal_synergy")
    profile["plans"] = frozenset(plans)
    profile["primary_tribe"] = strategy_tribe

    tribe_tag = f"tribe_{strategy_tribe}"
    required_tags = dict(profile.get("required_tags", {}))
    required_tags[tribe_tag] = max(required_tags.get(tribe_tag, 0), 20)
    required_tags["draw"] = max(required_tags.get("draw", 0), 4)
    required_tags["removal"] = max(required_tags.get("removal", 0), 5)
    profile["required_tags"] = required_tags

    finisher_tags = set(profile.get("finisher_tags", frozenset({"wincon"})))
    finisher_tags.update({tribe_tag, "anthem", "wincon"})
    profile["finisher_tags"] = frozenset(finisher_tags)
    return profile


def _expand_strategy_keyword(word: str, seen: set[str] | None = None) -> list[str]:
    seen = seen or set()
    wl = word.lower().strip()
    if not wl or wl in seen:
        return []
    seen.add(wl)
    expanded = [wl]
    for child in STRATEGY_KEYWORD_EXPANSIONS.get(wl, []):
        expanded.extend(_expand_strategy_keyword(child, seen))
    return expanded


def build_strategy_matchers(strategy_words: list[str]) -> list[tuple]:
    """
    Compile per-word regex matchers for strategy scoring.

    Returns a list of (type_pat, oracle_pats, expanded_word, orig_keywords) tuples
    where orig_keywords is a frozenset of the user-entered words that produced this
    expanded sub-keyword. Duplicate expansions are merged so each oracle pattern is
    only evaluated once, but all originating keywords are tracked for coherence scoring.
    """
    # expanded_word → {type_pat, oracle_pats, originals: set}
    expanded_map: dict[str, dict] = {}
    for w in strategy_words:
        for expanded in _expand_strategy_keyword(w):
            wl = expanded.lower()
            if wl not in expanded_map:
                if wl in STRATEGY_ORACLE_ALIASES:
                    oracle_pats = [re.compile(p, re.IGNORECASE) for p in STRATEGY_ORACLE_ALIASES[wl]]
                    type_pat = (
                        re.compile(STRATEGY_TYPE_ALIASES[wl], re.IGNORECASE)
                        if wl in STRATEGY_TYPE_ALIASES else None
                    )
                elif wl in STRATEGY_TYPE_ALIASES:
                    type_pat = re.compile(STRATEGY_TYPE_ALIASES[wl], re.IGNORECASE)
                    oracle_pats = []
                else:
                    word_pat = re.compile(r'\b' + re.escape(wl.rstrip('s')) + r's?\b', re.IGNORECASE)
                    type_pat = word_pat
                    oracle_pats = [word_pat]
                expanded_map[wl] = {"type_pat": type_pat, "oracle_pats": oracle_pats, "originals": set()}
            expanded_map[wl]["originals"].add(w)

    return [
        (info["type_pat"], info["oracle_pats"], expanded, frozenset(info["originals"]))
        for expanded, info in expanded_map.items()
    ]


def strategy_match_groups(card: dict, matchers: list[tuple]) -> frozenset[str]:
    """Return the user-entered strategy groups matched by this card."""
    type_line = card.get("type_line") or ""
    oracle = card.get("oracle_text") or ""
    name = card.get("name") or ""
    matched_groups: set[str] = set()
    for type_pat, oracle_pats, _w, orig_words in matchers:
        if type_pat and type_pat.search(type_line):
            matched_groups.update(orig_words)
        elif any(p.search(oracle) for p in oracle_pats):
            matched_groups.update(orig_words)
        elif type_pat and type_pat.search(name):
            matched_groups.update(orig_words)
    return frozenset(matched_groups)


def strategy_blend_multiplier(
    matched_groups: frozenset[str],
    strategy_counts: Counter,
    selection_size: int,
    nonland_slots: int,
) -> float:
    """
    Reward cards that reinforce the dominant current strategy cluster.

    If the user supplied strategy terms, a card that strengthens the deck's
    emerging keyword focus should outperform a card that merely matches an
    isolated or weakly represented keyword.
    """
    if selection_size < 8 or not matched_groups:
        return 1.0

    dominant = max(strategy_counts.values(), default=0)
    if dominant <= 0:
        return 1.0

    avg_group = sum(strategy_counts.values()) / max(len(strategy_counts), 1)
    matched_score = sum(int(strategy_counts.get(group, 0)) for group in matched_groups) / max(len(matched_groups), 1)
    fill_ratio = min(1.0, selection_size / max(nonland_slots, 1))
    coherence = (matched_score - avg_group) / max(dominant, 1)
    multiplier = 1.0 + coherence * (0.18 + 0.12 * fill_ratio)

    # Intersection cards deserve extra weight once the deck's theme is visible.
    if len(matched_groups) >= 2:
        multiplier += min(0.10, 0.04 * (len(matched_groups) - 1))

    return max(0.82, min(1.28, multiplier))


def card_matches_strategy(card: dict, matchers: list[tuple]) -> bool:
    """Return True if the card matches any strategy matcher (type_line or oracle)."""
    return bool(strategy_match_groups(card, matchers))


# ── Change 2: Format-legality filter constants ──────────────────────────────
ILLEGAL_LAYOUTS: frozenset[str] = frozenset({
    "sticker", "token", "emblem", "art_series", "double_faced_token",
    "scheme", "plane", "phenomenon", "vanguard",
})
ILLEGAL_TYPE_TOKENS: frozenset[str] = frozenset({
    "Sticker", "Token", "Emblem",
})
_ILLEGAL_ORACLE_RE = re.compile(
    r"\b(un-?set|silver-?border(?:ed)?|acorn stamp)\b", re.I
)
SILVER_BORDER_SETS: frozenset[str] = frozenset({
    "UGL", "UNH", "UND", "UST", "UNF",
})


def load_card_database() -> dict[str, dict]:
    """Load card database from bundle JSON (fast) or individual files (fallback)."""
    # Prefer pre-built bundle: data/cards_commander.json (already processed, ~18 MB)
    bundle_path = os.path.join(os.path.dirname(__file__), "data", "cards_commander.json")
    if os.path.isfile(bundle_path):
        with open(bundle_path, encoding="utf-8") as f:
            return json.load(f)

    # Fallback: load from individual card files (dev / first-run)
    if not os.path.isdir(CARDS_DIR):
        sys.exit(
            f"Error: card directory not found at '{CARDS_DIR}'.\n"
            "Run scripts/bundle_cards.py first to build the bundle, or\n"
            "run fetch_commander.py to download Commander-legal cards."
        )

    db: dict[str, dict] = {}
    for filename in os.listdir(CARDS_DIR):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(CARDS_DIR, filename)
        try:
            with open(filepath, encoding="utf-8") as f:
                card = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        # Double-faced cards: merge front-face fields upward so mana_cost etc. are accessible
        if "card_faces" in card and not card.get("mana_cost"):
            front = card["card_faces"][0]
            card = {**card, **{k: v for k, v in front.items() if k not in card or not card[k]}}

        # Change 2: broad format-legality filter
        if card.get("layout") in ILLEGAL_LAYOUTS:
            continue
        type_line_raw = card.get("type_line") or ""
        if any(tok in type_line_raw for tok in ILLEGAL_TYPE_TOKENS):
            continue
        if card.get("set", "").upper() in SILVER_BORDER_SETS:
            continue

        name = card.get("name", "").strip()
        if name:
            db[name] = card

    return db


# ─────────────────────────────────────────────────────────────────────────────
# BRAWL / COMMANDER HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def is_commander_eligible(card: dict) -> bool:
    """True if the card can serve as a Commander commander."""
    type_line = card.get("type_line") or ""
    return "Legendary" in type_line and (
        "Creature" in type_line or "Planeswalker" in type_line
    )


def get_color_identity(card: dict) -> set[str]:
    """Return the card's color identity as a set of single-letter color codes."""
    return set(card.get("color_identity") or [])


def fits_color_identity(card: dict, identity: set[str]) -> bool:
    """True if the card's color identity is a subset of the commander's identity."""
    return get_color_identity(card).issubset(identity | {"C"})


def get_all_commanders(db: dict) -> list[dict]:
    """Return all commander-eligible cards from the database, sorted by name."""
    return sorted(
        (c for c in db.values() if is_commander_eligible(c)),
        key=lambda c: c.get("name", ""),
    )


def _extract_primary_tribe(type_line: str) -> str | None:
    """Extract first meaningful creature subtype token from a type line."""
    _noise = {"the", "and", "of"}
    for face_type in (type_line or "").lower().split("//"):
        if "—" not in face_type:
            continue
        subtype_part = face_type.split("—", 1)[1].strip()
        for st in subtype_part.split():
            st = st.strip().lower()
            if st and len(st) > 2 and st not in _noise:
                return st
    return None


def _commander_tribal_signaled(oracle: str, primary_tribe: str | None) -> bool:
    """Whether commander text explicitly indicates tribe-matters gameplay."""
    if not primary_tribe:
        return False
    tribe_pat = re.escape(primary_tribe)
    if re.search(rf"\b{tribe_pat}s?\b", oracle):
        return True
    if re.search(
        r"choose a creature type|of the chosen type|share a creature type|creatures? of the chosen type",
        oracle,
    ):
        return True
    return False


def commander_auto_strategy(commander: dict, ignore_tribal: bool = False) -> str:
    """
    Derive automatic strategy keywords from the commander's type line and oracle text.
    Returns a space-separated string of hints to be merged with the user's strategy.
    """
    hints: set[str] = set()
    type_line = (commander.get("type_line") or "").lower()
    oracle    = (commander.get("oracle_text") or "").lower()
    keywords  = [k.lower() for k in (commander.get("keywords") or [])]

    # Tribal subtype hints are only added when the commander text explicitly
    # signals tribe-matters gameplay. A bare subtype alone should not steer.
    if not ignore_tribal:
        primary_tribe = _extract_primary_tribe(type_line)
        if _commander_tribal_signaled(oracle, primary_tribe) and primary_tribe:
            hints.add(primary_tribe)

    # Mechanic detection from oracle text.
    # Keep this intentionally conservative: auto-strategy should describe the
    # commander's primary engine, not every incidental rider in the textbox.
    if re.search(r"sacrifice (another|a|an|target)|whenever .{0,30} you control dies", oracle):
        hints.add("sacrifice")
    if re.search(r"from your graveyard|return .{0,30} graveyard|cast .{0,30} from your graveyard|whenever .{0,30} leaves your graveyard", oracle):
        hints.add("graveyard")
    if re.search(r"create .{0,30}token|tokens? you control", oracle):
        hints.add("tokens")
    if re.search(r"\+1/\+1 counter|proliferate|put (?:one or more |a |an )?.{0,20}counter.{0,20} on", oracle):
        hints.add("counters")
    if re.search(r"whenever you gain life|you gain \d+ life", oracle):
        hints.add("lifegain")
    if re.search(r"whenever you cast (?:an? )?(?:instant|sorcery|noncreature|spell)|magecraft|prowess|copy target spell", oracle):
        hints.add("spells")
    if re.search(r"artifact spells? you cast|whenever .{0,30}artifact enters|artifacts? you control|affinity for artifacts|improvise", oracle):
        hints.add("artifacts")
    if re.search(r"constellation|enchantments? you control|whenever .{0,20}enchantment enters", oracle):
        hints.add("enchantments")
    if re.search(r"whenever .{0,30}land enters|landfall", oracle):
        hints.add("landfall")
    if re.search(r"enters the battlefield|whenever .{0,30} enters the battlefield|flicker|blink", oracle):
        hints.add("etb")
    if re.search(r"whenever a creature dies|whenever .{0,30} dies", oracle):
        hints.add("sacrifice")

    return " ".join(sorted(hints))


def remove_tribal_plan_bias(plan_profile: dict[str, object] | None) -> dict[str, object]:
    """Return a copy of the plan profile with tribal-only steering removed."""
    plan_profile = dict(plan_profile or {})
    plans = set(plan_profile.get("plans", frozenset()))
    plans.discard("tribal_synergy")
    plan_profile["plans"] = frozenset(plans)

    primary_tribe = plan_profile.get("primary_tribe")
    plan_profile["primary_tribe"] = None

    required_tags = dict(plan_profile.get("required_tags", {}))
    if primary_tribe:
        required_tags.pop(f"tribe_{primary_tribe}", None)
    plan_profile["required_tags"] = required_tags

    finisher_tags = {
        tag for tag in set(plan_profile.get("finisher_tags", frozenset({"wincon"})))
        if not str(tag).startswith("tribe_")
    }
    if "wincon" not in finisher_tags:
        finisher_tags.add("wincon")
    plan_profile["finisher_tags"] = frozenset(finisher_tags)
    return plan_profile


def infer_commander_plan(commander: dict | None) -> dict[str, object]:
    """Infer structural deck requirements from the commander's text and body."""
    if commander is None:
        return {
            "plans": frozenset(),
            "required_tags": {},
            "finisher_tags": frozenset({"wincon"}),
        }

    oracle = (commander.get("oracle_text") or "").lower()
    type_line = (commander.get("type_line") or "").lower()
    keywords = [k.lower() for k in (commander.get("keywords") or [])]

    plans: set[str] = set()
    required_tags: dict[str, int] = {}
    finisher_tags: set[str] = {"wincon"}

    def add_plan(name: str, needs: dict[str, int], finishers: set[str] | None = None):
        plans.add(name)
        for tag, count in needs.items():
            required_tags[tag] = max(required_tags.get(tag, 0), count)
        if finishers:
            finisher_tags.update(finishers)

    # Require genuine GY exploitation — not just incidental "put into graveyard" text
    # (e.g. Choco puts non-land cards to GY as part of a land-search effect; that's
    # not graveyard_value). Require "from your graveyard" (returning/casting from GY),
    # "whenever .* dies" (death triggers), or explicit sacrifice-outlet patterns.
    if re.search(
        r"from (a |your |their )?graveyard"           # casting/returning from GY
        r"|whenever .{0,30} dies"                      # death trigger on the commander
        r"|sacrifice (a |an |target )"                 # sacrifice outlet
        r"|when .{0,30} is put into .{0,15}graveyard", # explicit GY payoff
        oracle,
    ):
        add_plan(
            "graveyard_value",
            {
                "graveyard_enabler": 6,
                "graveyard_payoff": 5,
                "self_mill": 4,           # need dedicated library→graveyard effects
                "sacrifice": 3,
                "death_trigger": 2,
            },
            {"death_trigger", "graveyard_payoff"},
        )

    if re.search(r"whenever you cast|instant or sorcery|prowess|magecraft", oracle):
        add_plan(
            "spells_velocity",
            {
                "spells_enabler": 14,
                "spells_payoff": 4,
                "draw": 6,
            },
            {"spells_payoff"},
        )

    if re.search(r"token|create .* token", oracle):
        add_plan(
            "go_wide_tokens",
            {
                "token_maker": 7,
                "token_payoff": 3,
                "anthem": 2,
            },
            {"anthem", "token_payoff"},
        )

    if re.search(r"artifact|historic|affinity|improvise", oracle) or "artifact" in type_line:
        add_plan(
            "artifact_engine",
            {
                "artifact": 8,
                "artifact_payoff": 3,
            },
            {"artifact_payoff"},
        )

    if re.search(r"enchantment|constellation", oracle):
        add_plan(
            "enchantment_engine",
            {
                "enchantment": 7,
                "enchantment_payoff": 3,
            },
            {"enchantment_payoff"},
        )

    if re.search(r"\+1/\+1 counter|proliferate|put .{0,15}counter.{0,10} on", oracle) or "proliferate" in keywords:
        add_plan(
            "counters_engine",
            {
                "counters": 7,
                "modified_enabler": 3,
            },
            {"counters", "modified_payoff"},
        )
    # If counters are only a rider on spell-casting triggers, treat them as a
    # subtheme of spellslinger instead of a co-equal primary engine.
    if "spells_velocity" in plans and "counters_engine" in plans:
        spell_counter_only = re.search(
            r"whenever you cast (?:an? )?(?:instant|sorcery|noncreature).{0,80}counter",
            oracle,
        ) and not re.search(
            r"proliferate|double .{0,20}counters?|move .{0,20}counters?|"
            r"whenever .{0,40}(?:another creature|a creature you control|target creature).{0,30}\+1/\+1 counter",
            oracle,
        )
        if spell_counter_only:
            plans.discard("counters_engine")
            required_tags.pop("counters", None)
            required_tags.pop("modified_enabler", None)
            finisher_tags.discard("modified_payoff")
            finisher_tags.discard("counters")

    if re.search(r"whenever a creature enters|enters the battlefield|flicker|blink", oracle):
        add_plan(
            "etb_value",
            {
                "etb_trigger": 7,
                "blink_enabler": 2,
            },
            {"etb_payoff", "blink_enabler"},
        )

    # Tribal plan: only infer tribe when the commander text actually signals
    # tribe-matters gameplay. A bare creature subtype (e.g. Centaur/Wizard) is
    # not enough by itself.
    primary_tribe = _extract_primary_tribe(type_line)
    tribal_signaled = _commander_tribal_signaled(oracle, primary_tribe)

    if primary_tribe and tribal_signaled:
        tribe_tag = f"tribe_{primary_tribe}"
        add_plan(
            "tribal_synergy",
            {
                tribe_tag: 20,
                "draw": 4,
                "removal": 5,
            },
            {tribe_tag, "anthem", "wincon"},
        )

    # Combat-damage engine: commander triggers on dealing combat damage to a player.
    # Covers: Yuriko, Gishath, Etali, Najeela, Bident of Thassa, Admiral Beckett, etc.
    if re.search(
        r"whenever .{0,60}deals combat damage"
        r"|whenever .{0,60}deals damage to (a player|an opponent)",
        oracle,
    ):
        add_plan(
            "combat_damage_engine",
            {
                "combat_damage_trigger": 3,
                "evasion": 8,           # enough unblockable/flying enablers
                "ninjutsu_enabler": 4,  # 1-drop evasive creatures for ninjutsu-style
                "draw": 4,
                "removal": 4,
            },
            {"combat_damage_trigger", "evasion", "wincon"},
        )

    # Exile-zone play: commander exiles cards and lets you cast them from exile.
    # Covers: Prosper, Laelia, Gonti, Etali, Ragavan, Kaldra Compleat-type builds.
    if re.search(
        r"exile the top .{0,30}card.{0,30}cast"
        r"|you may (cast|play) .{0,50}from exile"
        r"|exile .{0,30}you may cast .{0,30}(until end of turn|as long as)"
        r"|exile .{0,30}face down",
        oracle,
    ):
        add_plan(
            "exile_zone_play",
            {
                "exile_enabler": 6,
                "cast_from_exile": 4,
                "draw": 4,
                "removal": 4,
            },
            {"cast_from_exile", "exile_enabler", "wincon"},
        )

    # Spell-cost engine: commander reduces cost of spells, enabling high spell velocity.
    # Covers: Baral, Goblin Electromancer, Jhoira, Urza, Vadrik, Zada.
    if re.search(
        r"spells? you cast cost .{0,15}less"
        r"|(?:instant|sorcery|noncreature|artifact|creature|legendary|historic|equipment|aura|enchantment) spells? you cast cost .{0,15}less",
        oracle,
    ):
        add_plan(
            "spell_cost_engine",
            {
                "spells_enabler": 12,   # need many cheap spells
                "cost_reduction": 3,    # additional cost reducers
                "spells_payoff": 4,
                "draw": 6,
            },
            {"spells_payoff", "wincon"},
        )

    # Voltron engine: commander or build relies on auras/equipment to win via one threat.
    # Covers: Bruna, Sram, Galea, Rafiq, Uril, Kemba, Valduk.
    if re.search(
        r"enchant .{0,20}creature|whenever .{0,30}(equipped|enchanted).{0,30}attacks?"
        r"|whenever .{0,30}becomes (equipped|enchanted)"
        r"|whenever you (attach|cast .{0,10}(aura|equipment))",
        oracle,
    ) or ("equipment" in type_line and re.search(r"equipped creature.{0,20}gets \+", oracle)):
        add_plan(
            "voltron_engine",
            {
                "voltron_enabler": 10,  # auras/equipment
                "evasion": 4,           # give the voltron target evasion
                "keyword_grant": 3,
                "removal": 5,
            },
            {"voltron_enabler", "keyword_grant", "wincon"},
        )

    # Lands engine: beyond simple landfall — extra land drops, lands from graveyard,
    # land-based mana generation scaling with land count.
    # Covers: Gitrog, Omnath (all versions), Tatyova, Averna, Azusa, Mina & Denn, Choco.
    if re.search(
        r"\blandfall\b"                                # explicit Landfall keyword
        r"|whenever a land .{0,20}enters"              # landfall trigger (any wording)
        r"|you may play .{0,10}additional land"        # extra land drops
        r"|land.{0,30}from (your )?graveyard"          # lands from GY
        r"|whenever you play a land|whenever you put a land",
        oracle,
    ):
        add_plan(
            "lands_engine",
            {
                "extra_land_drop": 5,
                "land_ramp": 6,
                "landfall": 5,
                "draw": 4,
            },
            {"landfall", "lands_graveyard_payoff", "wincon"},
        )

    if not plans:
        add_plan(
            "midrange_value",
            {
                "draw": 5,
                "removal": 6,
                "threat": 10,
            },
            {"threat"},
        )

    return {
        "plans": frozenset(plans),
        "required_tags": required_tags,
        "finisher_tags": frozenset(finisher_tags),
        "primary_tribe": primary_tribe,
    }


PLAN_PRIORITY_RULES: dict[str, dict[str, object]] = {
    "graveyard_value": {
        "core_tags": {"graveyard_enabler", "graveyard_payoff", "sac_outlet", "self_mill"},
        # ramp and removal are universal infrastructure — always supported, never off-plan
        "support_tags": {"death_trigger", "sacrifice", "draw", "removal", "ramp"},
        "closure_tags": {"death_trigger", "graveyard_payoff", "wincon"},
        "redundancy": {"graveyard_enabler": 6, "graveyard_payoff": 5, "sac_outlet": 3,
                       "self_mill": 4, "death_trigger": 2, "removal": 4, "ramp": 8},
    },
    "spells_velocity": {
        "core_tags": {"spells_enabler", "spells_payoff"},
        "support_tags": {"draw", "removal", "ramp"},
        "closure_tags": {"spells_payoff", "wincon"},
        # Raised spells_enabler target: spellslinger decks need 15+ instants/sorceries,
        # not just 9. The higher target creates selection pressure throughout all phases.
        "redundancy": {"spells_enabler": 20, "spells_payoff": 5, "draw": 6,
                       "removal": 4, "ramp": 7},
    },
    "go_wide_tokens": {
        "core_tags": {"token_maker", "token_payoff"},
        "support_tags": {"anthem", "draw", "removal", "ramp"},
        "closure_tags": {"anthem", "token_payoff", "wincon"},
        "redundancy": {"token_maker": 7, "token_payoff": 3, "anthem": 2,
                       "removal": 4, "ramp": 8},
    },
    "artifact_engine": {
        "core_tags": {"artifact", "artifact_payoff"},
        "support_tags": {"draw", "removal", "ramp"},
        "closure_tags": {"artifact_payoff", "wincon"},
        "redundancy": {"artifact": 8, "artifact_payoff": 3, "removal": 4, "ramp": 8},
    },
    "enchantment_engine": {
        "core_tags": {"enchantment", "enchantment_payoff"},
        "support_tags": {"draw", "removal", "ramp"},
        "closure_tags": {"enchantment_payoff", "wincon"},
        "redundancy": {"enchantment": 7, "enchantment_payoff": 3, "removal": 4, "ramp": 7},
    },
    "counters_engine": {
        "core_tags": {"counters", "modified_enabler"},
        "support_tags": {"draw", "removal", "ramp"},
        "closure_tags": {"modified_payoff", "counters", "wincon"},
        "redundancy": {"counters": 6, "modified_enabler": 3, "removal": 4, "ramp": 8},
    },
    "etb_value": {
        "core_tags": {"etb_trigger"},
        "support_tags": {"blink_enabler", "draw", "removal", "ramp"},
        "closure_tags": {"etb_payoff", "wincon"},
        "redundancy": {"etb_trigger": 7, "blink_enabler": 2, "removal": 4, "ramp": 8},
    },
    "midrange_value": {
        "core_tags": {"draw"},
        "support_tags": {"removal", "threat", "ramp"},
        "closure_tags": {"wincon", "threat"},
        "redundancy": {"draw": 5, "removal": 5, "threat": 9, "ramp": 10},
    },
    # tribal_synergy: core_tags is intentionally empty here; the dynamic tribe
    # tag (e.g. "tribe_elf") is injected at runtime by derive_priority_profile()
    # because it depends on the commander's subtype.
    "tribal_synergy": {
        "core_tags": set(),
        "support_tags": {"draw", "anthem", "removal", "ramp"},
        "closure_tags": {"anthem", "wincon"},
        "redundancy": {"draw": 4, "removal": 4, "ramp": 7},
    },
    "combat_damage_engine": {
        "core_tags": {"evasion", "combat_damage_trigger"},
        "support_tags": {"draw", "removal", "extra_combat", "ramp"},
        "closure_tags": {"extra_combat", "wincon"},
        "redundancy": {"evasion": 8, "combat_damage_trigger": 3, "ninjutsu_enabler": 4,
                       "draw": 4, "removal": 4, "ramp": 7},
    },
    "exile_zone_play": {
        "core_tags": {"exile_enabler", "cast_from_exile"},
        "support_tags": {"draw", "removal", "top_manipulation", "ramp"},
        "closure_tags": {"cast_from_exile", "wincon"},
        "redundancy": {"exile_enabler": 6, "cast_from_exile": 4, "draw": 4,
                       "removal": 4, "ramp": 7},
    },
    "spell_cost_engine": {
        "core_tags": {"spells_enabler", "cost_reduction"},
        "support_tags": {"draw", "spells_payoff", "removal", "ramp"},
        "closure_tags": {"spells_payoff", "wincon"},
        # Raised spells_enabler target to ensure a true spell-dense build
        "redundancy": {"spells_enabler": 20, "cost_reduction": 3, "spells_payoff": 5,
                       "draw": 7, "removal": 4, "ramp": 7},
    },
    "voltron_engine": {
        "core_tags": {"voltron_enabler"},
        "support_tags": {"evasion", "keyword_grant", "removal", "ramp"},
        "closure_tags": {"voltron_enabler", "keyword_grant", "wincon"},
        "redundancy": {"voltron_enabler": 10, "evasion": 4, "keyword_grant": 3,
                       "removal": 5, "ramp": 7},
    },
    "lands_engine": {
        "core_tags": {"extra_land_drop", "landfall", "land_ramp"},
        "support_tags": {"draw", "removal", "ramp"},
        "closure_tags": {"landfall", "wincon"},
        "redundancy": {"extra_land_drop": 5, "land_ramp": 6, "landfall": 5,
                       "draw": 4, "removal": 4},
    },
}

PLAN_ENGINE_RULES: dict[str, dict[str, object]] = {
    "graveyard_value": {
        "components": (
            ("yard_fill", frozenset({"graveyard_enabler", "self_mill"}), 8),
            ("self_mill", frozenset({"self_mill"}), 4),          # mandatory dedicated mill
            ("recursion", frozenset({"graveyard_payoff"}), 5),
            ("outlets", frozenset({"sac_outlet"}), 3),
            ("payoffs", frozenset({"death_trigger"}), 2),
        ),
        "closure_tags": frozenset({"graveyard_payoff", "death_trigger", "wincon"}),
    },
    "spells_velocity": {
        "components": (
            ("cheap_spells", frozenset({"spells_enabler"}), 14),
            ("payoffs", frozenset({"spells_payoff"}), 4),
            ("velocity", frozenset({"draw"}), 5),
        ),
        "closure_tags": frozenset({"spells_payoff", "wincon"}),
    },
    "go_wide_tokens": {
        "components": (
            ("makers", frozenset({"token_maker"}), 7),
            ("payoffs", frozenset({"token_payoff"}), 3),
            ("closers", frozenset({"anthem"}), 2),
        ),
        "closure_tags": frozenset({"anthem", "token_payoff", "wincon"}),
    },
    "artifact_engine": {
        "components": (
            ("artifacts", frozenset({"artifact"}), 8),
            ("payoffs", frozenset({"artifact_payoff"}), 3),
            ("support", frozenset({"draw", "token_maker"}), 3),
        ),
        "closure_tags": frozenset({"artifact_payoff", "wincon"}),
    },
    "enchantment_engine": {
        "components": (
            ("enchantments", frozenset({"enchantment"}), 7),
            ("payoffs", frozenset({"enchantment_payoff"}), 3),
            ("support", frozenset({"draw", "token_maker"}), 3),
        ),
        "closure_tags": frozenset({"enchantment_payoff", "wincon"}),
    },
    "counters_engine": {
        "components": (
            ("counter_sources", frozenset({"counters"}), 6),
            ("modifiers", frozenset({"modified_enabler"}), 3),
            ("payoffs", frozenset({"modified_payoff"}), 2),
        ),
        "closure_tags": frozenset({"modified_payoff", "counters", "wincon"}),
    },
    "etb_value": {
        "components": (
            ("etb_bodies", frozenset({"etb_trigger"}), 7),
            ("blink", frozenset({"blink_enabler"}), 2),
            ("payoffs", frozenset({"etb_payoff", "draw"}), 3),
        ),
        "closure_tags": frozenset({"etb_payoff", "wincon"}),
    },
    "midrange_value": {
        "components": (
            ("threats", frozenset({"threat"}), 10),
            ("cards", frozenset({"draw"}), 5),
            ("interaction", frozenset({"removal", "disruption"}), 5),
        ),
        "closure_tags": frozenset({"threat", "wincon"}),
    },
    # tribal_synergy: tribe_members component uses an empty frozenset as
    # placeholder; plan_component_summary patches it at evaluation time using
    # plan_profile["primary_tribe"].
    "tribal_synergy": {
        "components": (
            ("tribe_members", frozenset(), 20),
            ("support", frozenset({"draw", "removal"}), 5),
            ("closers", frozenset({"anthem", "wincon"}), 2),
        ),
        "closure_tags": frozenset({"anthem", "wincon"}),
    },
    "combat_damage_engine": {
        "components": (
            ("evasion_suite", frozenset({"evasion", "ninjutsu_enabler"}), 10),
            ("triggers",      frozenset({"combat_damage_trigger"}), 3),
            ("support",       frozenset({"draw", "removal"}), 6),
            ("closers",       frozenset({"extra_combat", "wincon"}), 2),
        ),
        "closure_tags": frozenset({"extra_combat", "combat_damage_trigger", "wincon"}),
    },
    "exile_zone_play": {
        "components": (
            ("exile_sources",  frozenset({"exile_enabler"}), 6),
            ("exile_casters",  frozenset({"cast_from_exile"}), 4),
            ("support",        frozenset({"draw", "top_manipulation"}), 5),
            ("closers",        frozenset({"wincon"}), 1),
        ),
        "closure_tags": frozenset({"cast_from_exile", "wincon"}),
    },
    "spell_cost_engine": {
        "components": (
            ("cheap_spells",    frozenset({"spells_enabler"}), 12),
            ("reducers",        frozenset({"cost_reduction"}), 3),
            ("payoffs",         frozenset({"spells_payoff"}), 4),
            ("velocity",        frozenset({"draw"}), 6),
        ),
        "closure_tags": frozenset({"spells_payoff", "wincon"}),
    },
    "voltron_engine": {
        "components": (
            ("equipment_auras", frozenset({"voltron_enabler"}), 10),
            ("evasion",         frozenset({"evasion", "keyword_grant"}), 5),
            ("protection",      frozenset({"removal"}), 5),
        ),
        "closure_tags": frozenset({"voltron_enabler", "wincon"}),
    },
    "lands_engine": {
        "components": (
            ("extra_drops",   frozenset({"extra_land_drop"}), 5),
            ("land_fetch",    frozenset({"land_ramp"}), 6),
            ("payoffs",       frozenset({"landfall"}), 5),
            ("velocity",      frozenset({"draw"}), 4),
        ),
        "closure_tags": frozenset({"landfall", "lands_graveyard_payoff", "wincon"}),
    },
}

_TRIBAL_STRONG_ANTAGONIST_PLANS = frozenset({
    "spells_velocity",
    "spell_cost_engine",
})
_TRIBAL_ORTHOGONAL_PLANS = frozenset({
    "lands_engine",
    "artifact_engine",
    "enchantment_engine",
    "graveyard_value",
    "exile_zone_play",
    "voltron_engine",
})
_GENERIC_INFRA_TAGS = frozenset({"draw", "removal", "ramp"})


def _tribal_cap_for_plans(plans: frozenset[str]) -> int:
    """Cap tribal density based on how antagonistic the companion plans are."""
    nontribal = set(plans) - {"tribal_synergy"}
    if not nontribal:
        return 20
    if nontribal & _TRIBAL_STRONG_ANTAGONIST_PLANS:
        return 8
    if nontribal & _TRIBAL_ORTHOGONAL_PLANS:
        return 10
    return 12


def _tribal_member_target(plan_profile: dict[str, object] | None, default: int = 20) -> int:
    primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    if not primary_tribe:
        return default
    tribe_tag = f"tribe_{primary_tribe}"
    redundancy_targets = derive_priority_profile(plan_profile).get("redundancy_targets", {})
    return max(6, int(redundancy_targets.get(tribe_tag, default)))


def _scaled_tribal_target(base_target: int, tribal_alignment: float, plans: frozenset[str]) -> int:
    """
    Scale tribal density target by how often tribe cards also advance non-tribal
    core plans. Poor overlap means lower target to avoid subtype-only filler.
    """
    base_target = max(0, int(base_target))
    if base_target <= 0:
        return 0
    nontribal = set(plans) - {"tribal_synergy"}
    if not nontribal:
        return base_target
    factor = 1.0
    if tribal_alignment < 0.25:
        factor = 0.55
    elif tribal_alignment < 0.40:
        factor = 0.68
    elif tribal_alignment < 0.55:
        factor = 0.82
    elif tribal_alignment < 0.70:
        factor = 0.92
    scaled = int(math.ceil(base_target * factor))
    floor = 6 if "tribal_synergy" in plans else 0
    return max(floor, min(base_target, scaled))


def _tribal_alignment_ratio(
    primary_tribe: str | None,
    plans: list[str],
    candidate_cards: list[dict],
    tag_index: dict[str, frozenset[str]],
) -> float:
    """
    How well tribe creatures in pool overlap non-tribal core plan tags.
    Low ratio means tribal membership likely competes for slots without helping
    the other active plans.
    """
    if not primary_tribe or not candidate_cards or not plans:
        return 1.0
    tribe_tag = f"tribe_{primary_tribe}"
    tribe_creatures = [
        c for c in candidate_cards
        if is_creature(c) and tribe_tag in tag_index.get(c.get("name", ""), frozenset())
    ]
    if not tribe_creatures:
        return 0.0
    other_core: set[str] = set()
    for plan in plans:
        if plan == "tribal_synergy":
            continue
        rule = PLAN_PRIORITY_RULES.get(plan)
        if not rule:
            continue
        other_core.update(set(rule["core_tags"]) - _GENERIC_INFRA_TAGS)
    if not other_core:
        return 1.0
    hits = sum(
        1 for c in tribe_creatures
        if tag_index.get(c.get("name", ""), frozenset()) & other_core
    )
    return hits / max(1, len(tribe_creatures))


def derive_priority_profile(plan_profile: dict[str, object] | None) -> dict[str, object]:
    plans = frozenset((plan_profile or {}).get("plans", frozenset()))
    required_tags = dict((plan_profile or {}).get("required_tags", {}))
    finisher_tags = set((plan_profile or {}).get("finisher_tags", frozenset({"wincon"})))
    primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    core_tags: set[str] = set()
    support_tags: set[str] = set()
    redundancy_targets: dict[str, int] = dict(required_tags)
    is_multi_plan = len(plans) > 1
    for plan in plans:
        rule = PLAN_PRIORITY_RULES.get(plan)
        if not rule:
            continue
        if plan == "tribal_synergy" and primary_tribe:
            # Inject the runtime tribe tag — the static rule leaves core_tags
            # empty because the subtype isn't known at module load time.
            tribe_tag = f"tribe_{primary_tribe}"
            core_tags.add(tribe_tag)
            finisher_tags.add(tribe_tag)
            # When tribal is one plan among several, scale back the tribe density
            # target so it doesn't crowd out the other plan's engine pieces.
            # Solo tribal → 20 members; shared plan → 12 (healthy presence, not a flood).
            tribe_target = 12 if is_multi_plan else 20
            redundancy_targets[tribe_tag] = max(redundancy_targets.get(tribe_tag, 0), tribe_target)
        else:
            core_tags.update(rule["core_tags"])
        support_tags.update(rule["support_tags"])
        finisher_tags.update(rule["closure_tags"])
        for tag, count in rule["redundancy"].items():
            redundancy_targets[tag] = max(redundancy_targets.get(tag, 0), count)
    # Cap tribal density based on how antagonistic companion plans are.
    if is_multi_plan and primary_tribe:
        tribe_tag = f"tribe_{primary_tribe}"
        if tribe_tag in redundancy_targets:
            cap = _tribal_cap_for_plans(plans)
            redundancy_targets[tribe_tag] = min(cap, redundancy_targets[tribe_tag])

    support_tags -= core_tags
    return {
        "core_tags": frozenset(core_tags),
        "support_tags": frozenset(support_tags),
        "closure_tags": frozenset(finisher_tags),
        "redundancy_targets": redundancy_targets,
    }


def choose_active_packages(
    plan_profile: dict[str, object] | None,
    candidate_cards: list[dict],
    tag_index: dict[str, frozenset[str]],
) -> dict[str, object]:
    plans = list((plan_profile or {}).get("plans", frozenset()))
    if not plans:
        return {
            "primary_plan": None,
            "secondary_plan": None,
            "allowed_tags": frozenset(),
            "discouraged_tags": frozenset(),
            "tribal_alignment": 1.0,
        }

    primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    pool_counts = _tag_counter_from_cards(candidate_cards, tag_index)
    tribal_alignment = _tribal_alignment_ratio(primary_tribe, plans, candidate_cards, tag_index)
    scored_plans: list[tuple[float, str]] = []
    for plan in plans:
        rule = PLAN_PRIORITY_RULES.get(plan)
        if not rule:
            continue
        score = 0.0
        if plan == "tribal_synergy" and primary_tribe:
            # Score using the dynamic tribe tag in addition to static redundancy
            tribe_tag = f"tribe_{primary_tribe}"
            have = pool_counts.get(tribe_tag, 0)
            score += min(1.0, have / 20)
            for tag, target in rule["redundancy"].items():
                score += min(1.0, pool_counts.get(tag, 0) / max(1, target))
            score += 0.35 * (pool_counts.get(tribe_tag, 0) > 0)
        else:
            for tag, target in rule["redundancy"].items():
                have = pool_counts.get(tag, 0)
                score += min(1.0, have / max(1, target))
        score += 0.35 * sum(pool_counts.get(tag, 0) > 0 for tag in rule["closure_tags"])
        if plan == "tribal_synergy" and "tribal_synergy" in plans and len(plans) > 1:
            if tribal_alignment < 0.25:
                score *= 0.48
            elif tribal_alignment < 0.40:
                score *= 0.62
            elif tribal_alignment < 0.55:
                score *= 0.78
        scored_plans.append((score, plan))

    if not scored_plans:
        return {
            "primary_plan": None,
            "secondary_plan": None,
            "allowed_tags": frozenset(),
            "discouraged_tags": frozenset(),
            "tribal_alignment": tribal_alignment,
        }

    scored_plans.sort(reverse=True)
    primary = scored_plans[0][1]
    secondary = None
    if len(scored_plans) > 1 and scored_plans[1][0] >= scored_plans[0][0] * 0.7:
        secondary = scored_plans[1][1]

    allowed_tags: set[str] = set()
    discouraged_tags: set[str] = set()
    for plan in plans:
        rule = PLAN_PRIORITY_RULES.get(plan)
        if not rule:
            continue
        tags = set(rule["core_tags"]) | set(rule["support_tags"]) | set(rule["closure_tags"])
        if plan == "tribal_synergy" and primary_tribe:
            tags.add(f"tribe_{primary_tribe}")
        if plan == primary or plan == secondary:
            allowed_tags.update(tags)
        else:
            discouraged_tags.update(tags)

    discouraged_tags -= allowed_tags
    return {
        "primary_plan": primary,
        "secondary_plan": secondary,
        "allowed_tags": frozenset(allowed_tags),
        "discouraged_tags": frozenset(discouraged_tags),
        "tribal_alignment": tribal_alignment,
    }


def plan_component_summary(
    tag_counts: Counter,
    plan_profile: dict[str, object] | None,
    package_profile: dict[str, object] | None = None,
) -> dict[str, object]:
    package_profile = package_profile or choose_active_packages(plan_profile, [], {})
    primary = package_profile.get("primary_plan")
    if not primary or primary not in PLAN_ENGINE_RULES:
        return {
            "primary_plan": primary,
            "components": [],
            "completion_ratio": 0.0,
            "closure_hits": 0,
        }

    rule = PLAN_ENGINE_RULES[primary]
    primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    components = []
    met = 0
    for label, tags, need in rule["components"]:
        # For tribal_synergy, the first component uses an empty placeholder;
        # patch it with the actual runtime tribe tag.
        if primary == "tribal_synergy" and label == "tribe_members" and primary_tribe:
            tags = frozenset({f"tribe_{primary_tribe}"})
            need = _tribal_member_target(plan_profile, default=need)
        have = sum(tag_counts.get(tag, 0) for tag in tags)
        ok = have >= need
        if ok:
            met += 1
        components.append((label, have, need, ok))
    closure_hits = sum(tag_counts.get(tag, 0) for tag in rule["closure_tags"])
    completion_ratio = met / max(1, len(rule["components"]))
    return {
        "primary_plan": primary,
        "components": components,
        "completion_ratio": completion_ratio,
        "closure_hits": closure_hits,
    }


def plan_cast_priority_bonus(
    card: dict,
    seen_tags: Counter,
    plan_profile: dict[str, object] | None,
    package_profile: dict[str, object] | None,
    tag_index: dict[str, frozenset[str]],
) -> float:
    package_profile = package_profile or choose_active_packages(plan_profile, [card], tag_index)
    primary = package_profile.get("primary_plan")
    if not primary or primary not in PLAN_ENGINE_RULES:
        return 0.0
    card_tags = tag_index.get(card["name"], frozenset())
    rule = PLAN_ENGINE_RULES[primary]
    bonus = 0.0
    for _label, tags, need in rule["components"]:
        have = sum(seen_tags.get(tag, 0) for tag in tags)
        if have < need and card_tags & tags:
            bonus += (need - have) * 1.2
    if card_tags & frozenset(rule["closure_tags"]):
        completed = all(
            sum(seen_tags.get(tag, 0) for tag in tags) >= need
            for _label, tags, need in rule["components"]
        )
        if completed:
            bonus += 2.0
    return bonus


# ─────────────────────────────────────────────────────────────────────────────
# CARD PROPERTY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_cmc(card: dict) -> float:
    try:
        return float(card.get("cmc") or 0)
    except (TypeError, ValueError):
        return 0.0


def get_power(card: dict) -> int:
    try:
        return int(card.get("power") or 0)
    except (TypeError, ValueError):
        return 0


def get_toughness(card: dict) -> int:
    try:
        return int(card.get("toughness") or 0)
    except (TypeError, ValueError):
        return 0


def count_pips(mana_cost: str) -> dict[str, int]:
    """Count colored mana pips in a mana cost string, e.g. '{W}{W}{U}' → {W:2, U:1}."""
    pips: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
    for color in pips:
        pips[color] = mana_cost.count(f"{{{color}}}")
        # Also count hybrid pips as half each color — simplified to full here
        pips[color] += mana_cost.count(f"{{{color}/")
        pips[color] += mana_cost.count(f"/{color}}}")
    return pips


def is_land(card: dict) -> bool:
    return "Land" in card.get("type_line", "")


def is_creature(card: dict) -> bool:
    return "Creature" in card.get("type_line", "")


def is_noncreature_spell(card: dict) -> bool:
    return not is_land(card) and not is_creature(card)


def is_instant_or_sorcery(card: dict) -> bool:
    tl = card.get("type_line", "")
    return "Instant" in tl or "Sorcery" in tl


_SLOT_TYPES: tuple[str, str, str] = ("creature", "noncreature_spell", "other_permanent")


def _card_slot_kind(card: dict) -> str:
    if is_creature(card):
        return "creature"
    if is_instant_or_sorcery(card):
        return "noncreature_spell"
    return "other_permanent"


def _normalize_slot_mix(mix: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, float(mix.get(k, 0.0))) for k in _SLOT_TYPES)
    if total <= 0:
        return {k: 1.0 / len(_SLOT_TYPES) for k in _SLOT_TYPES}
    return {k: max(0.0, float(mix.get(k, 0.0))) / total for k in _SLOT_TYPES}


def _slot_mix_from_cards(cards: list[dict]) -> dict[str, float]:
    counts = {k: 0.0 for k in _SLOT_TYPES}
    if not cards:
        return _normalize_slot_mix(counts)
    for card in cards:
        counts[_card_slot_kind(card)] += 1.0
    return _normalize_slot_mix(counts)


def _build_tag_slot_affinity(
    cards: list[dict],
    tag_index: dict[str, frozenset[str]],
    baseline_mix: dict[str, float] | None = None,
) -> dict[str, dict[str, float]]:
    baseline_mix = baseline_mix or _slot_mix_from_cards(cards)
    tag_slot_counts: dict[str, dict[str, float]] = {}
    for card in cards:
        name = card.get("name", "")
        if not name:
            continue
        slot = _card_slot_kind(card)
        for tag in tag_index.get(name, frozenset()):
            slot_counts = tag_slot_counts.setdefault(tag, {k: 0.0 for k in _SLOT_TYPES})
            slot_counts[slot] += 1.0
    affinities: dict[str, dict[str, float]] = {}
    for tag, counts in tag_slot_counts.items():
        # Light smoothing around baseline avoids overfitting sparse tags.
        smoothed = {
            k: counts.get(k, 0.0) + baseline_mix.get(k, 0.0) * 1.2 + 0.05
            for k in _SLOT_TYPES
        }
        affinities[tag] = _normalize_slot_mix(smoothed)
    return affinities


def _slot_pressure_from_deficits(
    tag_counts: Counter,
    required_tags: dict[str, int],
    redundancy_targets: dict[str, int],
    core_tags: frozenset[str],
    tag_slot_affinity: dict[str, dict[str, float]],
    baseline_mix: dict[str, float],
) -> tuple[dict[str, float], frozenset[str], float]:
    pressure = {k: 0.0 for k in _SLOT_TYPES}
    unmet: set[str] = set()
    required_set = set(required_tags)
    all_tags = required_set | set(redundancy_targets) | set(core_tags)
    for tag in all_tags:
        need = max(required_tags.get(tag, 0), redundancy_targets.get(tag, 0))
        if need <= 0:
            continue
        have = int(tag_counts.get(tag, 0))
        deficit = max(0, need - have)
        if deficit <= 0:
            continue
        unmet.add(tag)
        weight = 1.5 if tag in core_tags else (1.15 if tag in required_set else 0.8)
        affinity = tag_slot_affinity.get(tag, baseline_mix)
        for slot in _SLOT_TYPES:
            pressure[slot] += deficit * weight * affinity.get(slot, 0.0)
    if not unmet:
        return _normalize_slot_mix(baseline_mix), frozenset(), 0.0
    total_need = sum(max(required_tags.get(t, 0), redundancy_targets.get(t, 0)) for t in unmet)
    total_deficit = sum(max(0, max(required_tags.get(t, 0), redundancy_targets.get(t, 0)) - int(tag_counts.get(t, 0))) for t in unmet)
    unresolved_ratio = total_deficit / max(1.0, float(total_need))
    return _normalize_slot_mix(pressure), frozenset(unmet), max(0.0, min(1.0, unresolved_ratio))


def _slot_pressure_adjustment(
    card: dict,
    contributes_unmet: bool,
    pressure_mix: dict[str, float],
    unresolved_ratio: float,
) -> float:
    kind = _card_slot_kind(card)
    desired = float(pressure_mix.get(kind, 0.0))
    max_desired = max(float(v) for v in pressure_mix.values())
    gap = max(0.0, max_desired - desired)
    if contributes_unmet:
        # Reward cards that fill unmet tags and align with pressured slot types.
        return (desired - (1.0 / 3.0)) * (1.2 + unresolved_ratio * 1.6)
    # Penalize cards that don't fill deficits and also occupy low-pressure slots.
    return -gap * (0.9 + unresolved_ratio * 2.1)


def get_subtypes(card: dict) -> set[str]:
    """Return creature / tribal subtypes from the type line."""
    tl = card.get("type_line", "")
    type_words = {
        "artifact", "battle", "conspiracy", "creature", "dungeon", "enchantment",
        "instant", "kindred", "land", "phenomenon", "plane", "planeswalker",
        "scheme", "sorcery", "tribal", "vanguard",
    }
    cleaned: set[str] = set()
    for face_type in tl.split("//"):
        if "—" not in face_type:
            continue
        supers, subs = face_type.split("—", 1)
        if not ("Creature" in supers or "Tribal" in supers):
            continue
        for token in subs.split():
            token = token.strip(" ,;:()[]{}").lower()
            if not token or not re.search(r"[a-z]", token):
                continue
            if token in type_words:
                continue
            cleaned.add(token.title())
    return cleaned


def fits_colors(card: dict, allowed: set[str]) -> bool:
    """True if the card's color identity is a subset of allowed colors + colorless."""
    return fits_color_identity(card, allowed)


# ─────────────────────────────────────────────────────────────────────────────
# CARD CLASSIFICATION — ROLES
# ─────────────────────────────────────────────────────────────────────────────

_REMOVAL_PATTERNS = re.compile(
    r"destroy target|exile target|deals? \d+ damage to target"
    r"|target creature gets? -\d+/-\d+|return target creature to"
    r"|tap target creature|target creature can't attack"
)
_SWEEP_PATTERNS = re.compile(
    r"destroy all|exile all creatures|each creature gets? -\d+/"
    r"|all creatures get -(?:\d+|x)|deals? \d+ damage to each creature"
    r"|return all creatures|return all .{0,20}permanents"
)
_RAMP_PATTERNS = re.compile(
    r"search your library for (?:up to \w+ )?(?:a )?(?:basic )?land"
    r"|search your library for a (?:plains|island|swamp|forest|mountain)\b"
    r"|put (?:a |that )?land (?:card )?(?:from[^.]*)?onto the battlefield"
    r"|you may play an additional land|untap target land"
    r"|adds? mana (?:of|in) (?:any|your)"
    r"|add (?:one|\d+|x) mana of any color"  # Arcane Signet / Birds-style templating
)
_DRAW_PATTERNS = re.compile(r"draw (?:a|two|three|four|\w+) cards?")
_DISCARD_PATTERNS = re.compile(r"target player discards?|each opponent discards?")
_TUTOR_PATTERNS = re.compile(
    r"search your library for (?:a |an )?(?:card|instant|sorcery|creature|artifact|enchantment)"
    r"(?! of the type)"
)
_COUNTER_PATTERNS = re.compile(r"counter target (?:spell|instant|sorcery|creature spell|activated)")
_THREAT_TEXT_PATTERNS = re.compile(
    r"deals? \d+ damage|target opponent|each opponent|can't block|can't attack"
    r"|draw a card|return target|destroy target|exile target|whenever .* dies"
)

_MILL_RE = re.compile(
    rf"\bmill {_NUMBER_WORD_RE} cards?\b"
    rf"|\bmills? cards?\b"
    rf"|each player mills?\b",
    re.IGNORECASE,
)


def classify_roles(card: dict) -> list[str]:
    """
    Classify a nonland card into one or more functional roles.
    Primary role is first in the list.
    Roles: threat, removal, sweeper, counterspell, draw, disruption, ramp, tutor, utility, wincon
    """
    roles: list[str] = []
    oracle = (card.get("oracle_text") or "").lower()
    keywords = [k.lower() for k in (card.get("keywords") or [])]
    type_line = card.get("type_line") or ""
    cmc = get_cmc(card)
    power = get_power(card)
    toughness = get_toughness(card)

    # ── Win condition ────────────────────────────────────────────────────────
    if "you win the game" in oracle:
        roles.append("wincon")

    # ── Threats ──────────────────────────────────────────────────────────────
    if is_creature(card):
        expected_stats = max(cmc * 2, 1)
        actual_stats = power + toughness
        has_defender = "defender" in keywords
        evasive = any(k in keywords for k in ("flying", "haste", "trample", "double strike", "menace"))
        generates_value = "when" in oracle and "enters" in oracle
        disruptive = bool(_THREAT_TEXT_PATTERNS.search(oracle))
        resilient = any(k in keywords for k in ("hexproof", "ward", "indestructible", "deathtouch", "lifelink"))
        is_efficient = actual_stats >= expected_stats or evasive or generates_value or resilient
        aggressive_two_drop = cmc <= 2 and (power >= 2 or evasive or disruptive)
        if not has_defender and (is_efficient or aggressive_two_drop):
            roles.append("threat")

    if "Planeswalker" in type_line:
        roles.append("threat")
        roles.append("draw")

    # ── Board wipes ──────────────────────────────────────────────────────────
    if _SWEEP_PATTERNS.search(oracle):
        roles.append("sweeper")
        roles.append("removal")

    # ── Targeted removal ─────────────────────────────────────────────────────
    if _REMOVAL_PATTERNS.search(oracle) and "counter target" not in oracle:
        if "removal" not in roles:
            roles.append("removal")

    # ── Counterspells ────────────────────────────────────────────────────────
    if _COUNTER_PATTERNS.search(oracle):
        roles.append("counterspell")

    # ── Card draw / selection ────────────────────────────────────────────────
    if _DRAW_PATTERNS.search(oracle):
        roles.append("draw")
    elif "scry" in oracle or "surveil" in oracle or ("draw" in oracle and "discard" in oracle):
        roles.append("draw")

    # ── Hand disruption ──────────────────────────────────────────────────────
    if _DISCARD_PATTERNS.search(oracle):
        roles.append("disruption")

    # ── Mana acceleration ────────────────────────────────────────────────────
    if _RAMP_PATTERNS.search(oracle):
        if not is_land(card):
            roles.append("ramp")
    # Mana dorks — detect "{T}: Add {G}" / "{T}: Add one mana of any color" etc.
    # Note: the old check used oracle.replace(" ","") which broke the string match.
    if is_creature(card) and re.search(r"\{t\}:\s*add\s*(?:\{|\w)", oracle):
        roles.append("ramp")
    # Mana rocks — CMC cap of 4 to include Thran Dynamo, Commander's Sphere, etc.
    if "Artifact" in type_line and re.search(r"\{t\}:\s*add", oracle) and cmc <= 4:
        roles.append("ramp")

    # ── Tutors ───────────────────────────────────────────────────────────────
    if _TUTOR_PATTERNS.search(oracle) and "land" not in oracle:
        roles.append("tutor")

    # ── Fallback ─────────────────────────────────────────────────────────────
    if not roles:
        roles.append("utility")

    return roles


# ─────────────────────────────────────────────────────────────────────────────
# SYNERGY TAGGING
# ─────────────────────────────────────────────────────────────────────────────

def detect_synergy_tags(card: dict) -> frozenset[str]:
    """Return a set of synergy category tags the card participates in."""
    tags: set[str] = set()
    oracle = (card.get("oracle_text") or "").lower()
    keywords = [k.lower() for k in (card.get("keywords") or [])]
    type_line = (card.get("type_line") or "").lower()
    subtypes = {s.lower() for s in get_subtypes(card)}

    # Tribal
    if get_subtypes(card):
        tags.add("tribal")

    # Tribe-specific membership tags: one per creature subtype so the plan
    # system can target a specific tribe as core_tags / redundancy_targets.
    for sub in subtypes:
        tags.add(f"tribe_{sub}")

    # Spells-matter
    if "prowess" in keywords:
        tags.add("spells_payoff")
    if re.search(r"whenever you cast (?:an? )?(?:instant|sorcery|noncreature)", oracle):
        tags.add("spells_payoff")
    if is_instant_or_sorcery(card):
        tags.add("spells_enabler")

    # Graveyard
    gy_keywords = {"flashback", "escape", "unearth", "delve", "threshold", "delirium",
                   "jump-start", "retrace", "dredge"}
    if any(k in keywords for k in gy_keywords) or re.search(
        r"cast .* from your graveyard|play .* from your graveyard|return target .* from your graveyard"
        r"|from your graveyard to your hand|from your graveyard to the battlefield",
        oracle,
    ):
        tags.add("graveyard_payoff")
    if (
        _MILL_RE.search(oracle)
        or re.search(
            r"put the top .{0,20} cards? of your library into your graveyard|surveil"
            r"|discard a card|discard one or more cards|draw .* discard"
            r"|search your library for .* put (?:it|them|that card) into your graveyard"
            r"|put (?:the rest|the remainder|the others) into your graveyard"
            r"|dredge \d+",
            oracle,
        )
    ):
        tags.add("graveyard_enabler")

    # Self-mill: specifically moves cards from your LIBRARY to graveyard.
    # Distinct from graveyard_enabler (which includes discard/loot) — Muldrotha
    # and similar commanders need library-to-graveyard specifically.
    if (
        _MILL_RE.search(oracle)
        or re.search(
            r"put the top .{0,20} cards? of your library into your graveyard"
            r"|your library into your graveyard"
            r"|dredge \d+|whenever .{0,40} is put into a graveyard from .{0,20}library",
            oracle,
        )
    ):
        tags.add("self_mill")
    if re.search(
        r"exile (?:all cards from all graveyards|all graveyards|target player.s graveyard|target card from a graveyard|target cards? from (?:a|all) graveyards?)"
        r"|cards? in graveyards can.t"
        r"|if (?:a|an) card would be put into a graveyard, exile it instead",
        oracle,
    ):
        tags.add("graveyard_hate")

    # Top-deck manipulation: arranges or looks at top of library.
    # Critical for commanders like Yuriko that trigger on top card damage.
    if re.search(
        r"look at the top \d+|scry \d+|put .{0,30}on top of (your|its owner.s) library"
        r"|arrange .{0,30}in any order|you may put .{0,50}on top"
        r"|search .{0,30}library .{0,30}put (it|that card) on top"
        r"|top of your library",
        oracle,
    ) or any(k in keywords for k in ("scry",)):
        tags.add("top_manipulation")

    # High-CMC bomb: expensive cards that can be cast for free or near-free.
    # Key for Yuriko (flip 8+ damage) and Grozoth-style high-CMC synergies.
    _cmc_val = float(card.get("cmc") or 0)
    if _cmc_val >= 7 and re.search(
        r"delve|affinity|convoke|evoke|suspend|cascade|pitch|free spell"
        r"|you may cast .{0,30}without paying"
        r"|pay \{0\}",
        oracle,
    ):
        tags.add("high_cmc_bomb")
    if _cmc_val >= 10:
        tags.add("high_cmc_bomb")  # anything 10+ is a flip target regardless

    # Tokens
    if "create" in oracle and "token" in oracle:
        tags.add("token_maker")
    if re.search(r"whenever a creature enters|whenever a token|for each creature you control", oracle):
        tags.add("token_payoff")

    # Sacrifice
    if "sacrifice" in oracle:
        tags.add("sacrifice")
    if re.search(r"sacrifice [^.\n]{0,40}:", oracle):
        tags.add("sac_outlet")
    if re.search(r"when(?:ever)? .{0,60} dies", oracle):
        tags.add("death_trigger")

    # Artifacts
    if "artifact" in type_line:
        tags.add("artifact")
    if "equipment" in type_line:
        tags.add("equipment")
    if "vehicle" in type_line:
        tags.add("vehicle")
    if re.search(r"affinity|improvise|for each artifact you control", oracle):
        tags.add("artifact_payoff")
    if re.search(r"crew \d+|return target vehicle|vehicle you control|whenever .*vehicle", oracle):
        tags.add("vehicle_payoff")
    if re.search(r"treasure|clue token|food token|blood token", oracle):
        tags.add("treasure_maker")
        tags.add("token_maker")

    # Enchantments / Constellation
    if "enchantment" in type_line:
        tags.add("enchantment")
    if "constellation" in keywords or "whenever an enchantment" in oracle:
        tags.add("enchantment_payoff")

    # Counters
    if "+1/+1 counter" in oracle:
        tags.add("counters")
    if "proliferate" in keywords:
        tags.add("counters")
    if "devotion to" in oracle:
        tags.add("devotion_payoff")
    if any(val >= 2 for val in count_pips(card.get("mana_cost") or "").values()):
        tags.add("heavy_pips")

    # ETB
    if is_creature(card) and re.search(r"when .{0,30} enters", oracle):
        tags.add("etb_trigger")
    if "whenever a creature enters" in oracle:
        tags.add("etb_payoff")
    if re.search(r"exile .{0,40} then return|blink|flicker", oracle):
        tags.add("blink_enabler")

    # Landfall
    if "landfall" in keywords or "whenever a land enters" in oracle:
        tags.add("landfall")
    if re.search(r"play lands? from your graveyard|return up to .* land cards? from your graveyard|land card from your graveyard", oracle):
        tags.add("lands_graveyard_payoff")

    # Anthems / go-wide payoffs
    if re.search(r"creatures you control get \+\d+/\+\d+", oracle):
        tags.add("anthem")

    # Surveil
    if re.search(r"whenever (you|a player) surveil", oracle):
        tags.add("surveil_payoff")
    elif "surveil" in keywords or "surveil" in oracle:
        tags.add("surveil_enabler")

    # Power-threshold activated abilities (e.g. Bloodshot Trainee)
    if re.search(r"activate only if .{0,80} has power [3-9]\d* or greater", oracle):
        tags.add("needs_power_boost")

    # Provides a meaningful power boost to another creature (equipment, auras, spells)
    if re.search(r"equipped creature gets \+[2-9]|\+[2-9]/\+[0-9]", oracle):
        tags.add("power_boost")
    if re.search(r"target creature gets \+[2-9]/\+[0-9] until end of turn", oracle):
        tags.add("power_boost")
    if re.search(r"gets? \+[2-9]/\+0", oracle) and not is_land(card):
        tags.add("power_boost")

    # Draw-payoffs (cards that reward drawing many cards, e.g. Ominous Seas)
    if re.search(r"whenever you draw (a card|your \w+ card each turn)", oracle):
        tags.add("draw_payoff")

    # Arcane / Spiritcraft
    if "spirit" in subtypes:
        tags.add("spirit_spell")
    if "arcane" in type_line:
        tags.add("arcane_spell")
    if re.search(r"target .*arcane card|arcane card from your graveyard|splice onto arcane", oracle):
        tags.add("arcane_payoff")
    if re.search(r"spirit or arcane spell|spiritcraft", oracle):
        tags.add("spiritcraft_payoff")

    # Historic (artifact, legendary, saga)
    if "saga" in type_line or ("artifact" in type_line and "creature" not in type_line and "{t}: add" not in oracle) or \
            ("legendary" in type_line and "land" not in type_line and "planeswalker" not in type_line):
        tags.add("historic_spell")
    if "historic" in oracle:
        tags.add("historic_payoff")

    # Energy
    if "{e}" in (card.get("mana_cost") or ""):
        tags.add("energy_payoff")
    if re.search(r"get (?:an |one |two |\d+ )?energy counters?", oracle):
        tags.add("energy_enabler")
    if "energy counter" in oracle and re.search(r"pay|spend|remove|lose", oracle):
        tags.add("energy_payoff")

    # Venture / dungeons
    if "venture into the dungeon" in oracle:
        tags.add("venture_enabler")
    if ("dungeon" in oracle and "venture into the dungeon" not in oracle) or \
            re.search(r"whenever you venture|completed a dungeon", oracle):
        tags.add("venture_payoff")

    # Modified
    if "modified" in oracle:
        tags.add("modified_payoff")
    if "equipment" in type_line or ("aura" in subtypes and "enchant creature" in oracle) or \
            re.search(r"attach target|equip \{|put (?:a|an|\d+) \+1/\+1 counter on target creature", oracle):
        tags.add("modified_enabler")

    # Equipment payoffs: cards that reward having Equipment or equipped creatures,
    # but are not themselves Equipment support pieces.
    if re.search(
        r"equipped creature|equipped creatures|for each equipment"
        r"|whenever .{0,30}becomes equipped|attach target equipment",
        oracle,
    ) and "equipment" not in type_line:
        tags.add("equipment_payoff")

    # Party
    for party_role in ("cleric", "rogue", "warrior", "wizard"):
        if party_role in subtypes:
            tags.add(f"party_{party_role}")
    if "party" in oracle:
        tags.add("party_payoff")

    # ── New systematic tags (covers ~35% of commanders missed by previous system) ──

    # Exile-zone play: exile cards from library/opponent, then cast from exile.
    # Covers: Prosper, Laelia, Gonti, Ragavan, Etali, Thief of Sanity type commanders.
    if re.search(
        r"exile the top .{0,20}card|exile .{0,30}at random"
        r"|you may (cast|play) .{0,40}(?:from exile|exiled with)"
        r"|play cards? exiled|cast .{0,30}from exile|cast .{0,30}face down",
        oracle,
    ):
        tags.add("exile_enabler")
    if re.search(
        r"you may (cast|play) .{0,40}from exile"
        r"|you may (cast|play) .{0,40}exiled"
        r"|plays? lands? and cast .{0,30}spell.{0,20}from exile"
        r"|impulse draw",
        oracle,
    ) or "discover" in keywords or "foretell" in keywords:
        tags.add("cast_from_exile")

    # Combat damage triggers: fires when dealing combat damage specifically.
    # Covers: Yuriko, Gishath, Etali, Najeela, Admiral Beckett Brass, Bident of Thassa.
    if re.search(
        r"whenever .{0,50}deals combat damage"
        r"|whenever .{0,50}deals damage to (a player|an opponent|the player)"
        r"|whenever .{0,50}deals (noncombat |combat )?damage to a player",
        oracle,
    ):
        tags.add("combat_damage_trigger")
    # Cards that help things connect / deal combat damage (unblockability, menace, etc.)
    if re.search(
        r"can't be blocked"
        r"|(?:shadow|horsemanship|skulk)\b"
        r"|all creatures able to block .{0,30}do so",
        oracle,
    ) or any(k in keywords for k in ("menace", "shadow", "horsemanship", "skulk", "trample",
                                       "flying", "fear", "intimidate")):
        if is_creature(card) or "equipment" in type_line or "aura" in type_line.replace("enchant", ""):
            tags.add("evasion")

    # Extra combat / untap-after-attack: Najeela, Aggravated Assault, Scourge of the Throne.
    if re.search(
        r"additional combat phase|untap all creatures that attacked"
        r"|take an extra combat|additional attack step"
        r"|untap all attacking creatures",
        oracle,
    ):
        tags.add("extra_combat")

    # Spell cost reduction: Baral, Jhoira, Goblin Electromancer, Urza, Zirda.
    if re.search(
        r"(?:spells?|instant|sorcery).{0,50}cost.{0,15}\{[0-9]\} less"
        r"|spells? you cast cost .{0,10}less"
        r"|reduce.{0,30}cost of .{0,30}spell"
        r"|abilities cost .{0,10} less",
        oracle,
    ):
        tags.add("cost_reduction")

    # Extra land drops: allows playing more than one land per turn.
    # Covers: Azusa, Oracle of Mul Daya, Cultivator Colossus, Exploration, Burgeoning.
    if re.search(
        r"you may play (?:an?|one|two|\d+) additional land"
        r"|play additional lands"
        r"|you may play a land (from|as though)",
        oracle,
    ):
        tags.add("extra_land_drop")
    # Landfall payoffs (already tag=landfall, adding to the lands_engine cluster)
    # Cards that put lands into play from hand/deck rapidly
    if re.search(
        r"put up to .{0,10}land.{0,30}onto the battlefield"
        r"|search your library for .{0,10}land.{0,30}put .{0,20}onto the battlefield",
        oracle,
    ):
        tags.add("land_ramp")  # distinct from ramp role: specifically lands-to-battlefield

    # Keyword grants to team: commanders that give all your creatures evasion/keywords.
    # Covers: Odric Lunarch Marshal, Akroma's Memorial, Radiant Destined, Archetype of Imagination.
    if re.search(
        r"creatures you control (?:gain|have|get).{0,60}"
        r"(?:flying|trample|menace|lifelink|deathtouch|first strike|double strike|haste|vigilance|hexproof|indestructible|shadow|unblockable)",
        oracle,
    ):
        tags.add("keyword_grant")

    # Voltron enablers: auras/equipment that specifically target/buff one creature.
    # Covers: Swiftfoot Boots, Lightning Greaves, Ethereal Armor, Colossification.
    if re.search(
        r"enchant creature|attach .{0,30}equip|equipped creature gets \+"
        r"|put .{0,10}equipment|equip \{",
        oracle,
    ) and ("equipment" in type_line or "aura" in type_line.replace("enchantment", "")):
        tags.add("voltron_enabler")
    if re.search(
        r"equipped creature gets \+[3-9]|\+[3-9]/\+[0-9].*equip"
        r"|enchanted creature gets \+[3-9]"
        r"|enchanted creature has .{0,40}(?:flying|double strike|trample|hexproof|indestructible)",
        oracle,
    ):
        tags.add("voltron_enabler")
    if re.search(
        r"equipped creature|equipped creatures|for each equipment"
        r"|whenever .{0,30}becomes equipped",
        oracle,
    ) and "equipment" not in type_line:
        tags.add("voltron_payoff")

    # Multicolor payoffs: rewards casting/having multicolored spells or permanents.
    # Covers: Ramos, Niv-Mizzet (Ravnica), Jodah, Jegantha.
    if re.search(
        r"whenever you cast a multicolored spell"
        r"|for each (?:different )?color|domain"
        r"|whenever you cast .{0,20}spell.{0,20}share.{0,20}color",
        oracle,
    ):
        tags.add("multicolor_payoff")

    # Domain: explicitly cares about controlling multiple basic land types.
    if "domain" in keywords or re.search(
        r"basic land types? (you|among lands you) control"
        r"|number of basic land types",
        oracle,
    ):
        tags.add("domain")

    # Life total as resource / life gain payoffs beyond simple lifegain.
    # Covers: Oloro, Willowdusk, Aetherflux Reservoir, necropotence-style builds.
    if re.search(
        r"pay \d+ life|pay X life|spend life"
        r"|you gain that much life"
        r"|if you have \d+ or more life"
        r"|your life total becomes",
        oracle,
    ):
        tags.add("life_as_resource")

    # Draw-count payoffs: trigger on Nth draw, reward drawing many cards in one turn.
    # Covers: Alandra, Lady Octopus, Kami of the Crescent Moon, The Locust God.
    if re.search(
        r"whenever you draw .{0,10}(?:second|third|fourth|5th|nth|your \w+ card)"
        r"|for each card (drawn|you've drawn)"
        r"|whenever you draw .{0,10}card beyond the first"
        r"|whenever you draw a card",
        oracle,
    ):
        tags.add("draw_count_payoff")

    # Ninjutsu enablers: small evasive creatures ideal for ninjutsu (Yuriko, Satoru).
    if "ninjutsu" in keywords or "ninjutsu" in oracle:
        tags.add("ninjutsu")
    # Ideal ninjutsu enablers: 1-drop evasive creatures
    if is_creature(card) and _cmc_val <= 1 and any(k in keywords for k in (
        "flying", "shadow", "skulk", "menace", "horsemanship", "intimidate", "fear"
    )):
        tags.add("ninjutsu_enabler")
    if is_creature(card) and _cmc_val <= 1 and re.search(r"can't be blocked", oracle):
        tags.add("ninjutsu_enabler")

    return frozenset(tags)


# ─────────────────────────────────────────────────────────────────────────────
# Change 5: Constructed-playability heuristic
# ─────────────────────────────────────────────────────────────────────────────

def score_constructed_playability(card: dict) -> float:
    """
    Return a heuristic playability bonus in [-2.0, +2.0] based on card
    design patterns that are broadly good in Commander without needing
    external win-rate data.

    Positive signals  → flexible, efficient, high-upside cards
    Negative signals  → narrow, parasitic, or symmetrical-disadvantage cards
    """
    oracle = (card.get("oracle_text") or "").lower()
    keywords = {k.lower() for k in (card.get("keywords") or [])}
    cmc = card.get("cmc") or 0
    type_line = (card.get("type_line") or "")
    is_creat = "Creature" in type_line

    score = 0.0

    # --- Positive: efficient card advantage ---
    if re.search(r"\bdraw (?:two|three|\d+) cards?\b", oracle):
        score += 0.6
    elif re.search(r"\bdraw a card\b", oracle):
        score += 0.3
    if re.search(r"\bsearch your library\b", oracle):
        score += 0.5
    if re.search(r"\breturn .{0,30} from your graveyard\b", oracle):
        score += 0.3

    # --- Positive: removal / disruption ---
    if re.search(r"\bdestroy target\b|\bexile target\b", oracle):
        score += 0.4
    if re.search(r"\bcounter target spell\b", oracle):
        score += 0.4

    # --- Positive: evasion on creatures ---
    if is_creat and any(k in keywords for k in ("flying", "trample", "menace", "deathtouch", "lifelink")):
        score += 0.25
    if is_creat and re.search(r"can't be blocked", oracle):
        score += 0.3

    # --- Positive: flexibility (modal / kick / X spells) ---
    if re.search(r"\bkicker\b|\bescalate\b|\bchoose one —|\bchoose two —|\bchoose up to\b", oracle):
        score += 0.35
    if cmc == 0 and re.search(r"\{x\}", (card.get("mana_cost") or "").lower()):
        score += 0.2  # X-cost spells (Cyclonic Rift style already has cmc > 0)

    # --- Positive: ETB value (already rewarded by tags; mild bonus here) ---
    if is_creat and re.search(r"when .{0,20} enters", oracle):
        score += 0.15

    # --- Negative: parasitic / build-around-only ---
    if re.search(r"\bfate counter\b|\bstory circle\b|\bpayoff only if\b", oracle):
        score -= 0.5
    if re.search(r"\bcards? with the same name\b|\bother cards? named\b", oracle):
        score -= 1.2
    # Un-set / acorn stamp already filtered; this catches edge cases
    if re.search(r"\bacorn\b", oracle) and "acorn" not in (card.get("name") or "").lower():
        score -= 1.0

    # --- Negative: heavy symmetry that helps opponents ---
    if re.search(r"each player draws\b|each player searches\b", oracle):
        score -= 0.5
    if re.search(r"each player (creates?|gets?|gains?).{0,20}token", oracle):
        score -= 0.3

    # --- Negative: high cmc with no immediate impact marker ---
    if cmc >= 7 and not re.search(
        r"\bdraw\b|\bsearch\b|\bdestroy\b|\bexile\b|\bcounter\b|\buntap\b", oracle
    ):
        score -= 0.4

    return max(-2.0, min(2.0, score))


# ─────────────────────────────────────────────────────────────────────────────
# Change 1: Named-card dependency extraction
# ─────────────────────────────────────────────────────────────────────────────

# Matches patterns like: "named Voltaic Key", "a card named Sol Ring"
# Captures the card name that follows "named".
_NAMED_CARD_RE = re.compile(
    r'\bnamed\s+"?([A-Z][A-Za-z\' ,\-]+?)"?'
    r'(?=\s*[,.\)]|\s+(?:is|are|that|which|you|in|on|to|from|with|when|if|and)\b)',
)


def extract_named_dependencies(card: dict) -> frozenset[str]:
    """
    Return a frozenset of card names that this card explicitly names in its
    oracle text (e.g. "named Sol Ring", "named Voltaic Key").
    These cards are treated as soft dependencies: if the dependency is absent
    from the deck, the card incurs a scoring penalty.
    """
    oracle = card.get("oracle_text") or ""
    return frozenset(m.group(1).strip() for m in _NAMED_CARD_RE.finditer(oracle))


# Synergy pair relationships: (source_tag, target_tag) — having both in a deck is good
SYNERGY_PAIRS: list[tuple[str, str]] = [
    ("spells_payoff",    "spells_enabler"),
    ("graveyard_payoff", "graveyard_enabler"),
    ("graveyard_payoff", "self_mill"),        # self-mill feeds GY payoffs
    ("token_maker",      "token_payoff"),
    ("token_maker",      "anthem"),
    ("artifact",         "artifact_payoff"),
    ("equipment",        "equipment_payoff"),
    ("enchantment",      "enchantment_payoff"),
    ("etb_trigger",      "etb_payoff"),
    ("etb_trigger",      "blink_enabler"),
    ("death_trigger",    "sacrifice"),
    ("treasure_maker",   "artifact_payoff"),
    ("surveil_payoff",   "surveil_enabler"),
    ("needs_power_boost","power_boost"),
    ("draw_payoff",      "graveyard_enabler"),  # draw-payoffs often pair with loot/fill effects
    ("top_manipulation", "graveyard_payoff"),   # Yuriko/top-deck synergy
    # New systematic pairs
    ("exile_enabler",    "cast_from_exile"),    # exile-zone play engine
    ("combat_damage_trigger", "evasion"),       # combat damage needs unblockable enablers
    ("ninjutsu_enabler", "combat_damage_trigger"),  # 1-drops carry ninjas in
    ("extra_combat",     "evasion"),            # extra attacks + unblockable
    ("cost_reduction",   "spells_enabler"),     # cost reducers need cheap spells to reduce
    ("spells_payoff",    "cost_reduction"),     # spell payoffs rewarded by cost engine
    ("extra_land_drop",  "landfall"),           # extra lands → more landfall triggers
    ("land_ramp",        "landfall"),           # fetching lands → landfall
    ("voltron_enabler",  "keyword_grant"),      # equip the creature, then grant evasion
    ("voltron_enabler",  "evasion"),            # voltron needs the threat to connect
    ("equipment",        "voltron_payoff"),     # equipped-creature payoffs need real equipment
    ("multicolor_payoff","draw"),               # multicolor decks want fixing + card draw
    ("draw_count_payoff","draw"),               # draw-count payoffs need draw engines
]

# Higher-order support/tension interactions used by selection and fitness.
# Fields: (signal_a, signal_b, min_a, min_b, weight)
SUPPORT_PAIR_WEIGHTS: list[tuple[str, str, int, int, float]] = [
    ("token_maker", "anthem", 6, 2, 1.2),
    ("token_maker", "death_trigger", 6, 2, 1.1),
    ("sac_outlet", "death_trigger", 3, 2, 1.3),
    ("self_mill", "graveyard_payoff", 4, 4, 1.3),
    ("graveyard_enabler", "graveyard_payoff", 6, 5, 1.4),
    ("blink_enabler", "etb_trigger", 3, 8, 1.3),
    ("spells_enabler", "spells_payoff", 12, 4, 1.25),
    ("combat_damage_trigger", "evasion", 4, 8, 1.2),
    ("landfall", "extra_land_drop", 5, 3, 1.2),
    ("landfall", "land_ramp", 5, 5, 1.1),
]

TENSION_PAIR_WEIGHTS: list[tuple[str, str, int, int, float]] = [
    ("token_maker", "sweeper", 6, 3, 1.35),
    ("voltron_enabler", "sweeper", 5, 3, 1.1),
    ("spells_enabler", "threat", 12, 24, 1.0),
    ("counterspell", "threat", 8, 24, 0.9),
    ("graveyard_payoff", "graveyard_hate", 4, 2, 1.6),
    ("self_mill", "graveyard_hate", 4, 2, 1.5),
]

# ─────────────────────────────────────────────────────────────────────────────
# KNOWN COMBO DATABASE
# Explicit two- (or three-) card combinations that produce a win or an engine.
# Each entry has:
#   "pieces"   — frozenset of exact card names
#   "type"     — "infinite_mana" | "instant_win" | "engine_loop" | "value_engine"
#   "tags"     — synergy tags to add to both pieces so the plan system rewards them
# When a deck contains one piece and the partner is in the candidate pool, the
# partner receives a strong selection bonus.  Full combo = large fitness bonus.
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_COMBOS: list[dict] = [
    # ── Infinite mana ────────────────────────────────────────────────────────
    {"pieces": frozenset({"Basalt Monolith", "Rings of Brighthearth"}),        "type": "infinite_mana"},
    {"pieces": frozenset({"Grim Monolith", "Power Artifact"}),                 "type": "infinite_mana"},
    {"pieces": frozenset({"Kinnan, Bonder Prodigy", "Basalt Monolith"}),       "type": "infinite_mana"},
    {"pieces": frozenset({"Dramatic Reversal", "Isochron Scepter"}),           "type": "infinite_mana"},
    {"pieces": frozenset({"Pemmin's Aura", "Zaxara, the Exemplary"}),          "type": "infinite_mana"},
    {"pieces": frozenset({"Pemmin's Aura", "Freed from the Real"}),            "type": "infinite_mana"},
    {"pieces": frozenset({"Training Grounds", "Maze of Ith"}),                 "type": "infinite_mana"},
    {"pieces": frozenset({"Selvala, Heart of the Wilds", "Umbral Mantle"}),    "type": "infinite_mana"},
    # ── Instant win ──────────────────────────────────────────────────────────
    {"pieces": frozenset({"Sanguine Bond", "Exquisite Blood"}),                "type": "instant_win"},
    {"pieces": frozenset({"Mikaeus, the Unhallowed", "Triskelion"}),           "type": "instant_win"},
    {"pieces": frozenset({"Mikaeus, the Unhallowed", "Walking Ballista"}),     "type": "instant_win"},
    {"pieces": frozenset({"Thassa's Oracle", "Tainted Pact"}),                 "type": "instant_win"},
    {"pieces": frozenset({"Thassa's Oracle", "Demonic Consultation"}),         "type": "instant_win"},
    {"pieces": frozenset({"Laboratory Maniac", "Demonic Consultation"}),       "type": "instant_win"},
    {"pieces": frozenset({"Helm of Obedience", "Rest in Peace"}),              "type": "instant_win"},
    {"pieces": frozenset({"Heliod, Sun-Crowned", "Walking Ballista"}),         "type": "instant_win"},
    {"pieces": frozenset({"Persist", "Cauldron of Souls"}),                    "type": "instant_win"},
    # ── Engine loops (repeatable value, not strictly infinite) ───────────────
    {"pieces": frozenset({"Ashnod's Altar", "Grave Titan"}),                   "type": "engine_loop"},
    {"pieces": frozenset({"Yawgmoth, Thran Physician", "Geralf's Messenger"}), "type": "engine_loop"},
    {"pieces": frozenset({"Birthing Pod", "Eternal Witness"}),                 "type": "engine_loop"},
    {"pieces": frozenset({"Sneak Attack", "Elvish Piper"}),                    "type": "engine_loop"},
    {"pieces": frozenset({"Splinter Twin", "Pestermite"}),                     "type": "instant_win"},
    {"pieces": frozenset({"Splinter Twin", "Deceiver Exarch"}),                "type": "instant_win"},
    {"pieces": frozenset({"Kiki-Jiki, Mirror Breaker", "Deceiver Exarch"}),    "type": "instant_win"},
    {"pieces": frozenset({"Kiki-Jiki, Mirror Breaker", "Pestermite"}),         "type": "instant_win"},
    # ── Value engines ─────────────────────────────────────────────────────────
    {"pieces": frozenset({"Food Chain", "Eternal Scourge"}),                   "type": "value_engine"},
    {"pieces": frozenset({"Bolas's Citadel", "Sensei's Divining Top"}),        "type": "value_engine"},
    {"pieces": frozenset({"Underworld Breach", "Brain Freeze"}),               "type": "instant_win"},
    {"pieces": frozenset({"Necropotence", "Bolas's Citadel"}),                 "type": "value_engine"},
]

# Reverse index: card name → list of combos it belongs to
_COMBO_INDEX: dict[str, list[dict]] = {}
for _combo in KNOWN_COMBOS:
    for _piece in _combo["pieces"]:
        _COMBO_INDEX.setdefault(_piece, []).append(_combo)


def combo_synergy_bonus(card_name: str, deck_names: list[str]) -> float:
    """
    Bonus for including a card that completes or partially assembles a known combo.
    Partial assembly (partner is in deck) gives a strong pull; full completion adds more.
    """
    if card_name not in _COMBO_INDEX:
        return 0.0
    deck_set = set(deck_names)
    bonus = 0.0
    for combo in _COMBO_INDEX[card_name]:
        other_pieces = combo["pieces"] - {card_name}
        have = sum(1 for p in other_pieces if p in deck_set)
        total_others = len(other_pieces)
        if have > 0:
            # Partial assembly: strong pull toward completion
            completion = have / total_others
            weight = 5.0 if combo["type"] == "instant_win" else 3.5
            bonus += completion * weight
    return bonus


def combo_completeness_bonus(deck_names: list[str]) -> float:
    """Fitness bonus for each fully assembled combo in the deck."""
    deck_set = set(deck_names)
    bonus = 0.0
    for combo in KNOWN_COMBOS:
        if all(p in deck_set for p in combo["pieces"]):
            weight = 8.0 if combo["type"] == "instant_win" else (
                6.0 if combo["type"] == "infinite_mana" else 4.0
            )
            bonus += weight
    return bonus


# ─────────────────────────────────────────────────────────────────────────────
# ENGINE FLOW SIMULATION
# Each plan type is modeled as an ordered chain of tiers:
#   fuel → engine → payload → win
# A tier is "satisfied" when the deck contains at least min_count cards with
# any of the tier's tags. The critical_gap is the first unsatisfied tier —
# this drives extra selection pressure during card selection and fitness scoring.
# ─────────────────────────────────────────────────────────────────────────────

ENGINE_FLOWS: dict[str, dict] = {
    # ── Tags used here map to BOTH detect_synergy_tags() output and classify_roles()
    # output (which is merged into tag_index at startup). Role tags available:
    #   wincon, ramp, draw, threat, removal, sweeper, counterspell, disruption, tutor, utility
    # Synergy tags are the full list from detect_synergy_tags().

    "graveyard_value": {
        "tiers": [
            # Fuel: fill the graveyard — self_mill, graveyard_enabler, draw-discard effects
            {"name": "fuel",    "tags": frozenset({"self_mill", "graveyard_enabler"}),                "min_count": 5, "weight": 1.0},
            # Engine: exploit the graveyard — sacrifice outlets + recursion
            {"name": "engine",  "tags": frozenset({"sac_outlet", "graveyard_payoff"}),               "min_count": 4, "weight": 1.5},
            # Payload: reward cards that need GY set up
            {"name": "payload", "tags": frozenset({"etb_trigger", "death_trigger", "sacrifice"}),    "min_count": 5, "weight": 1.3},
            # Win: any wincon, or high-cmc bombs reanimated for lethal
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "token_maker"}),       "min_count": 2, "weight": 2.0},
        ],
    },
    "spells_velocity": {
        "tiers": [
            # Fuel: draw cards and cantrips to keep spell count up
            {"name": "fuel",    "tags": frozenset({"draw", "spells_enabler"}),                       "min_count": 12, "weight": 1.0},
            # Engine: cost reduction + spells_enabler (instants/sorceries)
            {"name": "engine",  "tags": frozenset({"cost_reduction", "spells_enabler"}),             "min_count": 6, "weight": 1.5},
            # Payload: cards that reward casting spells
            {"name": "payload", "tags": frozenset({"spells_payoff"}),                                "min_count": 5, "weight": 1.3},
            # Win: wincon card or high-CMC spell bomb, or wincon role
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "spells_payoff"}),     "min_count": 2, "weight": 2.0},
        ],
    },
    "go_wide_tokens": {
        "tiers": [
            # Fuel: token producers
            {"name": "fuel",    "tags": frozenset({"token_maker"}),                                   "min_count": 8, "weight": 1.0},
            # Engine: cards that amplify token value
            {"name": "engine",  "tags": frozenset({"token_payoff", "anthem"}),                        "min_count": 4, "weight": 1.5},
            # Payload: pump effects and combat enablers
            {"name": "payload", "tags": frozenset({"anthem", "keyword_grant", "extra_combat"}),       "min_count": 4, "weight": 1.3},
            # Win: wincon role or extra_combat to swing for lethal
            {"name": "win",     "tags": frozenset({"wincon", "extra_combat", "token_payoff"}),        "min_count": 2, "weight": 2.0},
        ],
    },
    "artifact_engine": {
        "tiers": [
            # Fuel: artifacts (rocks, equipment, utility artifacts)
            {"name": "fuel",    "tags": frozenset({"artifact", "ramp"}),                              "min_count": 10, "weight": 1.0},
            # Engine: artifact payoffs that generate ongoing value
            {"name": "engine",  "tags": frozenset({"artifact_payoff"}),                              "min_count":  5, "weight": 1.5},
            # Payload: ETB effects from artifacts + threats
            {"name": "payload", "tags": frozenset({"etb_trigger", "artifact_payoff", "draw"}),        "min_count":  4, "weight": 1.3},
            # Win: wincon or high-cmc bomb
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count":  2, "weight": 2.0},
        ],
    },
    "enchantment_engine": {
        "tiers": [
            # Fuel: enchantments (auras, sagas, global)
            {"name": "fuel",    "tags": frozenset({"enchantment"}),                                   "min_count": 10, "weight": 1.0},
            # Engine: enchantment payoff cards (enchantress draw effects)
            {"name": "engine",  "tags": frozenset({"enchantment_payoff"}),                           "min_count":  5, "weight": 1.5},
            # Payload: auras that buff threats + voltron enablers
            {"name": "payload", "tags": frozenset({"voltron_enabler", "keyword_grant", "anthem"}),    "min_count":  4, "weight": 1.3},
            # Win: wincon or overwhelming threat
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count":  2, "weight": 2.0},
        ],
    },
    "counters_engine": {
        "tiers": [
            # Fuel: cards that put +1/+1 counters on things
            {"name": "fuel",    "tags": frozenset({"counters"}),                                      "min_count": 6, "weight": 1.0},
            # Engine: proliferate spreads counters to all permanents
            {"name": "engine",  "tags": frozenset({"counters", "draw_count_payoff"}),                 "min_count": 4, "weight": 1.5},
            # Payload: cards that scale with / reward counter counts
            {"name": "payload", "tags": frozenset({"draw_count_payoff", "token_maker"}),              "min_count": 5, "weight": 1.3},
            # Win: wincon or large threats grown by counters
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count": 2, "weight": 2.0},
        ],
    },
    "etb_value": {
        "tiers": [
            # Fuel: creatures with enters-the-battlefield effects
            {"name": "fuel",    "tags": frozenset({"etb_trigger"}),                                   "min_count": 10, "weight": 1.0},
            # Engine: blink/flicker enablers that replay ETBs
            {"name": "engine",  "tags": frozenset({"blink_enabler"}),                                 "min_count":  5, "weight": 1.5},
            # Payload: ETB payoff cards that multiply value
            {"name": "payload", "tags": frozenset({"etb_payoff", "etb_trigger", "draw"}),             "min_count":  6, "weight": 1.3},
            # Win: wincon or enough ETB damage/drain to close
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "etb_trigger"}),        "min_count":  2, "weight": 2.0},
        ],
    },
    "tribal_synergy": {
        "tiers": [
            # tribe_X tag is dynamic; filled in at validate_engine_flow() via plan_profile
            {"name": "fuel",    "tags": frozenset(),                                                   "min_count": 18, "weight": 1.0},
            # Engine: lords and anthems that reward playing the tribe
            {"name": "engine",  "tags": frozenset({"anthem", "keyword_grant"}),                       "min_count":  4, "weight": 1.5},
            # Payload: evasion and tribal synergy rewards
            {"name": "payload", "tags": frozenset({"evasion", "token_maker", "draw"}),                "min_count":  4, "weight": 1.3},
            # Win: wincon or extra combat to swing with the army
            {"name": "win",     "tags": frozenset({"wincon", "extra_combat", "high_cmc_bomb"}),       "min_count":  2, "weight": 2.0},
        ],
    },
    "midrange_value": {
        "tiers": [
            # Fuel: ramp spells and mana rocks
            {"name": "fuel",    "tags": frozenset({"ramp"}),                                          "min_count": 10, "weight": 1.0},
            # Engine: card draw to find threats and answers
            {"name": "engine",  "tags": frozenset({"draw"}),                                          "min_count":  7, "weight": 1.5},
            # Payload: impactful spells and removal
            {"name": "payload", "tags": frozenset({"removal", "threat"}),                             "min_count":  8, "weight": 1.3},
            # Win: wincon card or high-cmc threat
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count":  2, "weight": 2.0},
        ],
    },
    "combat_damage_engine": {
        "tiers": [
            # Fuel: evasive creatures + ninjutsu enablers (unblocked attackers)
            {"name": "fuel",    "tags": frozenset({"evasion", "ninjutsu_enabler"}),                   "min_count": 6, "weight": 1.0},
            # Engine: triggers on combat damage connecting
            {"name": "engine",  "tags": frozenset({"combat_damage_trigger", "ninjutsu"}),             "min_count": 6, "weight": 1.5},
            # Payload: reward cards for connecting (high-cmc bombs flip, draw)
            {"name": "payload", "tags": frozenset({"high_cmc_bomb", "draw", "extra_combat"}),         "min_count": 5, "weight": 1.3},
            # Win: wincon or extra combats to finish
            {"name": "win",     "tags": frozenset({"wincon", "extra_combat", "high_cmc_bomb"}),       "min_count": 2, "weight": 2.0},
        ],
    },
    "exile_zone_play": {
        "tiers": [
            # Fuel: exile-from-library effects
            {"name": "fuel",    "tags": frozenset({"exile_enabler", "top_manipulation"}),             "min_count": 6, "weight": 1.0},
            # Engine: cards that let you cast from exile
            {"name": "engine",  "tags": frozenset({"cast_from_exile"}),                               "min_count": 6, "weight": 1.5},
            # Payload: generate value from the exiled cards (treasure, etc.)
            {"name": "payload", "tags": frozenset({"treasure_maker", "draw", "etb_trigger"}),         "min_count": 5, "weight": 1.3},
            # Win: wincon or high-cmc threat cast for free
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count": 2, "weight": 2.0},
        ],
    },
    "spell_cost_engine": {
        "tiers": [
            # Fuel: cost-reduction effects
            {"name": "fuel",    "tags": frozenset({"cost_reduction"}),                                "min_count": 5, "weight": 1.0},
            # Engine: instants/sorceries to cast cheaply at volume
            {"name": "engine",  "tags": frozenset({"spells_enabler", "draw"}),                       "min_count": 12, "weight": 1.5},
            # Payload: cards that reward the spell volume
            {"name": "payload", "tags": frozenset({"spells_payoff"}),                                 "min_count": 5, "weight": 1.3},
            # Win: wincon, or enough spells_payoff damage to close
            {"name": "win",     "tags": frozenset({"wincon", "spells_payoff", "high_cmc_bomb"}),      "min_count": 2, "weight": 2.0},
        ],
    },
    "voltron_engine": {
        "tiers": [
            # Fuel: auras and equipment to stack on commander
            {"name": "fuel",    "tags": frozenset({"voltron_enabler"}),                               "min_count": 10, "weight": 1.0},
            # Engine: keyword grants that make the commander evasive/lethal
            {"name": "engine",  "tags": frozenset({"keyword_grant", "power_boost", "evasion"}),       "min_count":  5, "weight": 1.5},
            # Payload: tutors and draw to find the pieces
            {"name": "payload", "tags": frozenset({"draw", "tutor", "enchantment_payoff"}),           "min_count":  4, "weight": 1.3},
            # Win: voltron_enabler density = commander damage win; or wincon role
            {"name": "win",     "tags": frozenset({"wincon", "voltron_enabler", "keyword_grant"}),    "min_count":  2, "weight": 2.0},
        ],
    },
    "lands_engine": {
        "tiers": [
            # Fuel: extra land drops + land-fetch spells
            {"name": "fuel",    "tags": frozenset({"extra_land_drop", "land_ramp", "ramp"}),          "min_count": 8, "weight": 1.0},
            # Engine: landfall payoffs that generate value per land
            {"name": "engine",  "tags": frozenset({"landfall"}),                                      "min_count": 5, "weight": 1.5},
            # Payload: draw engines and large threats built on land count
            {"name": "payload", "tags": frozenset({"draw", "high_cmc_bomb", "token_maker"}),          "min_count": 5, "weight": 1.3},
            # Win: wincon or overwhelming threat
            {"name": "win",     "tags": frozenset({"wincon", "high_cmc_bomb", "threat"}),             "min_count": 2, "weight": 2.0},
        ],
    },
}

# Win condition taxonomy: maps win type to the tags/combos that enable it.
# Used by detect_win_conditions() to report which win paths are available.
WIN_CONDITION_REGISTRY: list[dict] = [
    {
        "name": "infinite_combo",
        "description": "Assemble a known infinite/instant-win combo",
        "check": "combo",   # special: checked against KNOWN_COMBOS
        "required_tags": frozenset(),
        "min_count": 0,
    },
    {
        "name": "combat_lethal",
        "description": "Win through creature combat damage",
        "check": "tags",
        # wincon role = "you win the game", high_cmc_bomb = big threats, extra_combat = finishing swings
        "required_tags": frozenset({"wincon", "high_cmc_bomb", "extra_combat", "threat"}),
        "min_count": 4,
    },
    {
        "name": "commander_damage",
        "description": "21 commander damage via voltron",
        "check": "tags",
        # voltron_enabler density + keyword grants = commander damage path
        "required_tags": frozenset({"voltron_enabler", "keyword_grant", "evasion"}),
        "min_count": 5,
    },
    {
        "name": "drain_loop",
        "description": "Repeatedly drain life (Sanguine Bond, aristocrats chains)",
        "check": "tags",
        # life_as_resource = drain/lifegain payoffs; sac_outlet = sacrifice loops
        "required_tags": frozenset({"life_as_resource", "sac_outlet", "death_trigger"}),
        "min_count": 4,
    },
    {
        "name": "token_army",
        "description": "Overwhelm with token creatures",
        "check": "tags",
        # token_maker + anthem to buff them + evasion or extra_combat to get through
        "required_tags": frozenset({"token_maker", "anthem", "extra_combat"}),
        "min_count": 6,
    },
    {
        "name": "spell_storm",
        "description": "High spell velocity for spells_payoff damage or card advantage",
        "check": "tags",
        # cost_reduction + spells_enabler mass + spells_payoff reward
        "required_tags": frozenset({"cost_reduction", "spells_enabler", "spells_payoff"}),
        "min_count": 5,
    },
    {
        "name": "mill_win",
        "description": "Mill opponents' libraries to win",
        "check": "tags",
        # self_mill + graveyard_payoff for self + wincon for actual mill win condition
        "required_tags": frozenset({"self_mill", "graveyard_payoff"}),
        "min_count": 5,
    },
    {
        "name": "card_dominance",
        "description": "Overwhelming card advantage until table concedes",
        "check": "tags",
        # heavy draw + draw_count_payoff (Blue Sun's Zenith style) + threats to close
        "required_tags": frozenset({"draw", "draw_count_payoff", "threat"}),
        "min_count": 8,
    },
]


def validate_engine_flow(
    tag_counts: "Counter",
    plan_name: str,
    plan_profile: dict | None = None,
) -> dict:
    """
    Evaluate how completely the deck satisfies its engine flow chain.

    Returns:
        tier_scores     : dict of tier_name → fraction satisfied [0.0–1.0]
        overall_score   : weighted average across all tiers [0.0–1.0]
        critical_gap    : name of the first tier below 50% completion (or None)
        critical_gap_tags: tag set of the critical gap tier (for selection pressure)
        gap_tier_weight  : weight of the critical gap tier
    """
    if plan_name not in ENGINE_FLOWS:
        return {
            "tier_scores": {},
            "overall_score": 1.0,
            "critical_gap": None,
            "critical_gap_tags": frozenset(),
            "gap_tier_weight": 0.0,
        }

    flow = ENGINE_FLOWS[plan_name]
    tiers = flow["tiers"]

    # Inject real tribe tag into tribal_synergy fuel tier
    if plan_name == "tribal_synergy" and plan_profile:
        primary_tribe = plan_profile.get("primary_tribe", "")
        if primary_tribe:
            tiers = list(tiers)
            tiers[0] = dict(tiers[0])
            tiers[0]["tags"] = frozenset({f"tribe_{primary_tribe}"})

    tier_scores: dict[str, float] = {}
    total_weight = 0.0
    weighted_score = 0.0
    critical_gap: str | None = None
    critical_gap_tags: frozenset = frozenset()
    gap_tier_weight = 0.0

    for tier in tiers:
        t_name = tier["name"]
        t_tags = tier["tags"]
        t_min = tier["min_count"]
        t_weight = tier["weight"]

        if not t_tags or t_min == 0:
            tier_scores[t_name] = 1.0
            total_weight += t_weight
            weighted_score += t_weight
            continue

        have = sum(tag_counts.get(tag, 0) for tag in t_tags)
        score = min(1.0, have / t_min)
        tier_scores[t_name] = score
        total_weight += t_weight
        weighted_score += score * t_weight

        if critical_gap is None and score < 0.5:
            critical_gap = t_name
            critical_gap_tags = t_tags
            gap_tier_weight = t_weight

    overall = weighted_score / total_weight if total_weight > 0 else 1.0

    return {
        "tier_scores": tier_scores,
        "overall_score": overall,
        "critical_gap": critical_gap,
        "critical_gap_tags": critical_gap_tags,
        "gap_tier_weight": gap_tier_weight,
    }


def detect_win_conditions(
    deck_names: list[str],
    tag_counts: "Counter",
) -> list[dict]:
    """
    Identify which win condition paths the deck has assembled.

    Returns a list of dicts: {name, description, available, notes}
    """
    deck_set = set(deck_names)
    results: list[dict] = []

    for wc in WIN_CONDITION_REGISTRY:
        available = False
        notes = ""

        if wc["check"] == "combo":
            for combo in KNOWN_COMBOS:
                if all(p in deck_set for p in combo["pieces"]):
                    available = True
                    notes = f"Combo assembled: {', '.join(sorted(combo['pieces']))}"
                    break
        else:
            # Tags check: how many cards contribute to required tags?
            req_tags = wc["required_tags"]
            count = sum(tag_counts.get(t, 0) for t in req_tags)
            if count >= wc["min_count"]:
                available = True
                notes = f"{count} cards support this path"

        results.append({
            "name": wc["name"],
            "description": wc["description"],
            "available": available,
            "notes": notes,
        })

    return results


# Payoff tags that require a matching enabler tag to be useful.
# Used in deck_fitness to penalize orphaned payoffs.
PAYOFF_ENABLER_PAIRS: list[tuple[str, str]] = [
    ("surveil_payoff",   "surveil_enabler"),
    ("needs_power_boost","power_boost"),
    ("spells_payoff",    "spells_enabler"),
    ("graveyard_payoff", "graveyard_enabler"),
    ("etb_payoff",       "etb_trigger"),
    ("enchantment_payoff","enchantment"),
    ("artifact_payoff",  "artifact"),
    ("equipment_payoff", "equipment"),
    ("token_payoff",     "token_maker"),
    ("draw_payoff",      "graveyard_enabler"),
]

# Narrow mechanics with explicit support requirements. These are the places
# where the generic payoff/enabler model is too weak and the generator can
# otherwise include dead cards such as Arcane payoffs with no Arcane spells.
NARROW_MECHANIC_RULES: dict[str, dict[str, object]] = {
    "arcane": {
        "support_tags": frozenset({"arcane_spell"}),
        "payoff_tags": frozenset({"arcane_payoff"}),
        "min_support": 4,
    },
    "spiritcraft": {
        "support_tags": frozenset({"arcane_spell", "spirit_spell"}),
        "payoff_tags": frozenset({"spiritcraft_payoff"}),
        "min_support": 7,
    },
    "historic": {
        "support_tags": frozenset({"historic_spell"}),
        "payoff_tags": frozenset({"historic_payoff"}),
        "min_support": 8,
    },
    "energy": {
        "support_tags": frozenset({"energy_enabler"}),
        "payoff_tags": frozenset({"energy_payoff"}),
        "min_support": 5,
    },
    "venture": {
        "support_tags": frozenset({"venture_enabler"}),
        "payoff_tags": frozenset({"venture_payoff"}),
        "min_support": 4,
    },
    "modified": {
        "support_tags": frozenset({"modified_enabler"}),
        "payoff_tags": frozenset({"modified_payoff"}),
        "min_support": 5,
    },
    "party": {
        "support_tags": frozenset({"party_cleric", "party_rogue", "party_warrior", "party_wizard"}),
        "payoff_tags": frozenset({"party_payoff"}),
        "min_support": 3,
    },
}

SUPPORT_VALIDATION_RULES: dict[str, dict[str, object]] = {
    "equipment": {
        "support_tags": frozenset({"equipment"}),
        "payoff_tags": frozenset({"equipment_payoff", "voltron_payoff"}),
        "min_support": 5,
    },
    "vehicle": {
        "support_tags": frozenset({"vehicle"}),
        "payoff_tags": frozenset({"vehicle_payoff"}),
        "min_support": 2,
    },
    "devotion": {
        "support_tags": frozenset({"heavy_pips"}),
        "payoff_tags": frozenset({"devotion_payoff"}),
        "min_support": 8,
    },
    "lands_graveyard": {
        "support_tags": frozenset({"graveyard_enabler", "landfall", "ramp"}),
        "payoff_tags": frozenset({"lands_graveyard_payoff"}),
        "min_support": 6,
    },
}

LIABILITY_WEIGHTS: dict[str, float] = {
    "donate_to_opponent": 4.5,
    "skip_turns": 7.5,
    "upkeep_burden": 3.5,
    "land_sacrifice": 3.0,
    "conditional_combat": 2.0,
    "solo_lock": 2.0,
    "forced_sacrifice": 3.0,
    "etb_sacrifice": 2.6,
    "forced_discard": 2.2,
    "lose_game": 8.0,
    "exile_library": 6.0,
    "self_wipe": 5.0,
}


def _tag_counter_from_cards(cards: list[dict], tag_index: dict[str, frozenset[str]]) -> Counter:
    counts: Counter = Counter()
    for card in cards:
        for tag in tag_index.get(card["name"], frozenset()):
            counts[tag] += 1
    return counts


def _signal_count(signal: str, tag_counts: Counter, role_counts: Counter | None = None) -> int:
    """Read a signal count from tags first, then roles for role-only signals."""
    if signal in tag_counts:
        return int(tag_counts.get(signal, 0))
    if role_counts is not None:
        return int(role_counts.get(signal, 0))
    return 0


def interaction_support_tension_adjustment(
    tag_counts: Counter,
    role_counts: Counter | None = None,
) -> tuple[float, float]:
    """Return (support_bonus, tension_penalty) from cross-mechanic interactions."""
    support_bonus = 0.0
    tension_penalty = 0.0

    for a, b, min_a, min_b, weight in SUPPORT_PAIR_WEIGHTS:
        have_a = _signal_count(a, tag_counts, role_counts)
        have_b = _signal_count(b, tag_counts, role_counts)
        if have_a <= 0 or have_b <= 0:
            continue
        sat_a = min(1.0, have_a / max(min_a, 1))
        sat_b = min(1.0, have_b / max(min_b, 1))
        support_bonus += sat_a * sat_b * weight

    for a, b, min_a, min_b, weight in TENSION_PAIR_WEIGHTS:
        have_a = _signal_count(a, tag_counts, role_counts)
        have_b = _signal_count(b, tag_counts, role_counts)
        if have_a < min_a or have_b < min_b:
            continue
        tension_a = (have_a - min_a + 1) / max(min_a, 1)
        tension_b = (have_b - min_b + 1) / max(min_b, 1)
        tension_penalty += min(3.5, tension_a * tension_b * weight)

    return support_bonus, tension_penalty


def _narrow_mechanic_adjustment(
    tag_counts: Counter,
    card_tags: frozenset[str] | None = None,
) -> float:
    """
    Score narrow mechanics based on whether the required shell actually exists.

    If card_tags is provided, returns the per-card adjustment for adding or
    evaluating that card against the available support. Without card_tags, this
    returns the deck-level package bonus/penalty.
    """
    adj = 0.0
    for rule in NARROW_MECHANIC_RULES.values():
        support_tags = rule["support_tags"]
        payoff_tags = rule["payoff_tags"]
        min_support = int(rule["min_support"])
        support = sum(tag_counts.get(tag, 0) for tag in support_tags)
        payoff = sum(tag_counts.get(tag, 0) for tag in payoff_tags)

        if card_tags is not None:
            if card_tags & payoff_tags:
                missing = max(0, min_support - support)
                adj -= missing * 1.4
                if support >= min_support:
                    adj += min(1.5, 0.25 * (support - min_support + 1))
            elif card_tags & support_tags and payoff > 0:
                adj += min(1.25, 0.2 * payoff)
            continue

        if payoff <= 0:
            continue

        missing = max(0, min_support - support)
        if missing > 0:
            adj -= missing * 1.1 + payoff * 0.35
        else:
            adj += min(2.5, 0.3 * payoff + 0.15 * (support - min_support))
    return adj


def _support_rule_adjustment(
    tag_counts: Counter,
    card_tags: frozenset[str] | None = None,
) -> float:
    adj = 0.0
    for rule in SUPPORT_VALIDATION_RULES.values():
        support_tags = rule["support_tags"]
        payoff_tags = rule["payoff_tags"]
        min_support = int(rule["min_support"])
        support = sum(tag_counts.get(tag, 0) for tag in support_tags)
        payoff = sum(tag_counts.get(tag, 0) for tag in payoff_tags)
        if card_tags is not None:
            if card_tags & payoff_tags:
                missing = max(0, min_support - support)
                adj -= missing * 1.3
                if support >= min_support:
                    adj += min(1.5, 0.25 * (support - min_support + 1))
            elif card_tags & support_tags and payoff > 0:
                adj += min(1.25, 0.2 * payoff)
            continue
        if payoff <= 0:
            continue
        missing = max(0, min_support - support)
        if missing > 0:
            adj -= missing * 1.2 + payoff * 0.5
        else:
            adj += min(2.0, 0.3 * payoff + 0.1 * (support - min_support))
    return adj


def detect_liability_flags(card: dict) -> frozenset[str]:
    oracle = (card.get("oracle_text") or "").lower()
    flags: set[str] = set()
    if re.search(r"target opponent gains control|an opponent gains control|target player gains control", oracle):
        flags.add("donate_to_opponent")
    if re.search(r"skip your next \w+ step|skip your next \d+ turns?|skip your next turn|you skip your next", oracle):
        flags.add("skip_turns")
    if re.search(r"at the beginning of your upkeep, sacrifice", oracle) or "cumulative upkeep" in oracle:
        flags.add("upkeep_burden")
    if re.search(r"at the beginning of your upkeep, discard a card|during your upkeep, discard", oracle):
        flags.add("forced_discard")
    if re.search(r"sacrifice a land", oracle):
        flags.add("land_sacrifice")
    if re.search(r"sacrifice all (?:permanents|creatures) you control", oracle):
        flags.add("self_wipe")
    if re.search(r"when(?:ever)? .{0,60}(?:enters the battlefield|deals combat damage).{0,50}sacrifice", oracle):
        flags.add("forced_sacrifice")
    if re.search(r"when(?:ever)? .{0,30} enters.{0,40}sacrifice (?:a|an|another) ", oracle) and "you may" not in oracle:
        flags.add("etb_sacrifice")
    if re.search(r"can't attack or block alone", oracle):
        flags.add("solo_lock")
    if re.search(
        r"can't (attack|block) (or block |or attack )?unless "
        r"(you.ve |you have |you control|a creature died|an? .{0,20} died)",
        oracle,
    ):
        flags.add("conditional_combat")
    if re.search(r"you lose the game|lose the game", oracle):
        flags.add("lose_game")
    if re.search(r"exile all cards from your library|exile your library|your library becomes your graveyard", oracle):
        flags.add("exile_library")
    return frozenset(flags)


def liability_penalty(card: dict) -> float:
    return sum(LIABILITY_WEIGHTS.get(flag, 0.0) for flag in detect_liability_flags(card))


def _weighted_pick(
    scored_cards: list[tuple[float, dict]],
    excluded: set[str],
    diversity: float,
    deck_names: list[str] | None = None,
    db: dict | None = None,
    tag_index: dict[str, frozenset[str]] | None = None,
    deck_tag_counts: Counter | None = None,
) -> dict | None:
    """Pick a card from the top of a scored list with weighted randomness."""
    available = [(sc, card) for sc, card in scored_cards if card["name"] not in excluded]
    if not available:
        return None
    window = min(len(available), max(5, int(5 + diversity * 6)))
    shortlist = available[:window]

    adjusted: list[tuple[float, dict]] = []
    for sc, card in shortlist:
        bonus = 0.0
        if deck_names and db is not None and tag_index is not None:
            bonus += synergy_added_by_card(card["name"], deck_names, db, tag_index) * 1.75
        if deck_tag_counts is not None and tag_index is not None:
            merged = Counter(deck_tag_counts)
            card_tags = tag_index.get(card["name"], frozenset())
            for tag in card_tags:
                merged[tag] += 1
            bonus += _narrow_mechanic_adjustment(merged, card_tags)
        adjusted.append((sc + bonus, card))

    adjusted.sort(key=lambda x: -x[0])
    if diversity <= 0:
        return adjusted[0][1]

    floor = min(sc for sc, _ in adjusted)
    sharpness = max(0.9, 2.2 - diversity * 0.35)
    weights = [max(0.05, sc - floor + 1.0) ** sharpness for sc, _ in adjusted]
    return random.choices([card for _sc, card in adjusted], weights=weights, k=1)[0]


def is_cheap_ramp_card(card: dict) -> bool:
    return "ramp" in classify_roles(card) and get_cmc(card) <= 3


def is_cheap_setup_card(card: dict) -> bool:
    tags = detect_synergy_tags(card)
    roles = classify_roles(card)
    return (
        get_cmc(card) <= 3 and (
            "draw" in roles or
            "graveyard_enabler" in tags or
            "spells_enabler" in tags or
            "token_maker" in tags or
            "ramp" in roles
        )
    )


def estimate_effective_turn(card: dict) -> float:
    """
    Estimate when a card is meaningfully deployed, rather than printed mana value.

    This captures alternate cheap modes (cycling, surveil/cantrip setup),
    reactive cards that often get held, and ramp that effectively lands early.
    """
    cmc = max(0.0, get_cmc(card))
    oracle = (card.get("oracle_text") or "").lower()
    keywords = {k.lower() for k in (card.get("keywords") or [])}
    roles = classify_roles(card)
    tags = detect_synergy_tags(card)

    effective = cmc
    if is_cheap_ramp_card(card):
        effective = min(effective, max(1.0, cmc - 0.8))
    if is_cheap_setup_card(card):
        effective = min(effective, max(1.0, cmc - 0.5))
    if "cycling" in keywords or "channel" in keywords:
        effective = min(effective, max(1.0, cmc - 1.0))
    if any(k in keywords for k in ("flashback", "escape", "unearth", "adventure")):
        effective = max(1.5, effective - 0.35)
    if "counterspell" in roles or ("removal" in roles and is_noncreature_spell(card)):
        effective += 0.35
    if "sweeper" in roles:
        effective += 0.75
    if "draw" in roles and get_cmc(card) >= 4:
        effective += 0.25
    if "graveyard_enabler" in tags and cmc <= 3:
        effective = min(effective, max(1.0, cmc - 0.4))
    return max(1.0, effective)


def quadrant_profile(card: dict) -> dict[str, float]:
    """
    Approximate quadrant-theory usefulness across opening/parity/behind/ahead/closing.
    """
    oracle = (card.get("oracle_text") or "").lower()
    roles = classify_roles(card)
    tags = detect_synergy_tags(card)
    cmc = get_cmc(card)
    power = get_power(card)

    opening = 0.0
    parity = 0.0
    behind = 0.0
    ahead = 0.0
    closing = 0.0

    if is_cheap_ramp_card(card) or is_cheap_setup_card(card):
        opening += 1.0
    if "draw" in roles and cmc <= 3:
        opening += 0.45
    if "tutor" in roles:
        parity += 0.55
        opening += 0.2
    if "removal" in roles or "counterspell" in roles or "disruption" in roles:
        parity += 0.8
    if "sweeper" in roles:
        behind += 1.3
    if "removal" in roles and cmc <= 3:
        behind += 0.45
    if "draw" in roles and cmc >= 3:
        parity += 0.55
    if "token_maker" in tags or "etb_trigger" in tags:
        parity += 0.35
        ahead += 0.35
    if "anthem" in tags or "token_payoff" in tags:
        ahead += 0.8
        closing += 0.45
    if "wincon" in roles or "wincon" in tags:
        closing += 1.4
    if "death_trigger" in tags or "graveyard_payoff" in tags:
        parity += 0.35
        closing += 0.35
    if is_creature(card) and power >= 4:
        ahead += 0.45
        closing += 0.55
    if "can't block" in oracle or "each opponent" in oracle:
        closing += 0.35
    if "lifelink" in {k.lower() for k in (card.get("keywords") or [])}:
        behind += 0.25

    return {
        "opening": opening,
        "parity": parity,
        "behind": behind,
        "ahead": ahead,
        "closing": closing,
    }


def estimate_color_pressure(nonlands: list[dict], colors: set[str], land_count: int) -> dict[str, float]:
    """
    Approximate colored-mana consistency before building the exact mana base.

    We use deck pip share as the expected source mix, then compare that to
    Karsten-style requirements for the most color-demanding early spell.
    """
    pip_totals: dict[str, int] = {c: 0 for c in ("W", "U", "B", "R", "G")}
    pip_demand: dict[str, dict[str, int]] = {c: {"pips": 0, "turn": 7} for c in colors}
    untapped_early_need = 0

    for card in nonlands:
        mana_cost = card.get("mana_cost") or ""
        pips = count_pips(mana_cost)
        effective_turn = max(1, min(7, int(round(estimate_effective_turn(card)))))
        if effective_turn <= 3 and any(pips.values()):
            untapped_early_need += 1
        for color, val in pips.items():
            pip_totals[color] += val
            if color not in colors or val <= 0:
                continue
            if val > pip_demand[color]["pips"] or (
                val == pip_demand[color]["pips"] and effective_turn < pip_demand[color]["turn"]
            ):
                pip_demand[color] = {"pips": val, "turn": effective_turn}

    active_total = sum(pip_totals[c] for c in colors) or 1
    reliability_total = 0.0
    shortages = 0.0
    checks = 0
    for color in colors:
        share = pip_totals[color] / active_total if active_total else 0.0
        expected_sources = land_count * share
        demand = pip_demand[color]
        if demand["pips"] <= 0:
            continue
        p_clamped = min(3, max(1, demand["pips"]))
        t_clamped = min(6, max(1, demand["turn"]))
        required = KARSTEN_SOURCES.get(p_clamped, {}).get(t_clamped, 12)
        scaled_required = required * (land_count / 24.0)
        softened_required = scaled_required * 0.82
        ratio = min(1.10, expected_sources / max(1.0, softened_required))
        reliability_total += ratio
        shortages += max(0.0, softened_required - expected_sources)
        checks += 1

    color_score = (reliability_total / checks) if checks else 1.0
    untapped_pressure = min(1.0, untapped_early_need / max(1, len(nonlands) // 6))
    return {
        "color_score": max(0.0, min(1.15, color_score)),
        "shortage": shortages,
        "untapped_pressure": untapped_pressure,
    }


def estimate_commander_land_count(
    nonlands: list[dict],
    commander: dict | None,
    archetype: str,
    plan_profile: dict | None = None,
) -> int:
    """
    Estimate Commander land count using Karsten-style heuristics.

    Baseline: 31.42 + 3.13 * avg_mana_value - 0.28 * cheap ramp/draw pieces
    Then apply commander/archetype/plan corrections and clamp to sane limits.
    """
    if not nonlands:
        return ARCHETYPE_CONFIG[archetype]["land_count"]

    all_spells = list(nonlands)
    if commander is not None:
        all_spells.append(commander)

    avg_mv = sum(get_cmc(c) for c in all_spells) / max(len(all_spells), 1)
    cheap_accel = sum(1 for c in nonlands if is_cheap_ramp_card(c) or is_cheap_setup_card(c))
    commander_mv = get_cmc(commander or {})

    estimate = 31.42 + 3.13 * avg_mv - 0.28 * cheap_accel
    if commander_mv >= 6:
        estimate += 1.0
    if archetype == "control":
        estimate += 1.0
    elif archetype == "aggro":
        estimate -= 1.0
    preliminary = max(31, min(40, round(estimate)))

    deck_colors = set()
    for card in nonlands:
        deck_colors |= set(card.get("color_identity") or [])
    if commander is not None:
        deck_colors |= set(commander.get("color_identity") or [])
    color_pressure = estimate_color_pressure(nonlands, deck_colors, preliminary)
    if len(deck_colors) >= 3 and color_pressure["color_score"] < 0.82:
        preliminary += 1
    if color_pressure["color_score"] < 0.72 or color_pressure["shortage"] > 6.0:
        preliminary += 1
    if color_pressure["untapped_pressure"] > 0.85 and len(deck_colors) >= 2:
        preliminary += 1

    # Plan-specific land floor adjustments:
    #   lands_engine: landfall decks want consistent land drops every turn — needs 38+
    #   graveyard_value: self-mill decks want a large library buffer — needs 36+
    #   combat_damage_engine: tempo/aggro with evasion — a little lighter is fine
    if plan_profile is not None:
        plans = plan_profile.get("plans", frozenset())
        if isinstance(plans, str):
            plans = frozenset({plans})
        if "lands_engine" in plans:
            preliminary = max(preliminary, 38)
        if "graveyard_value" in plans:
            preliminary = max(preliminary, 36)
        if "spell_cost_engine" in plans or "spells_velocity" in plans:
            # Spell-dense decks run lower land counts — they draw into action fast
            preliminary = min(preliminary, 36)

    return max(31, min(40, preliminary))


def simulate_commander_goldfish(
    nonlands: list[dict],
    commander: dict | None,
    land_count: int,
    tag_index: dict[str, frozenset[str]],
    plan_profile: dict[str, object] | None = None,
    trials: int = 18,
) -> dict[str, float]:
    """
    Lightweight goldfish simulation for early-turn consistency.

    This is intentionally approximate: it measures opening-hand stability,
    early action density, mana development, and commander deployment pace.
    """
    if commander is None:
        return {
            "dead_hand_rate": 0.0,
            "mean_mana_spent": 0.0,
            "mean_first_play_turn": 6.0,
            "commander_on_curve_rate": 0.0,
            "pair_assembly_rate": 0.0,
            "engine_completion_rate": 0.0,
            "finisher_seen_rate": 0.0,
        }

    key = (
        commander.get("name", ""),
        land_count,
        tuple(sorted(c["name"] for c in nonlands)),
    )
    cached = _GOLDFISH_CACHE.get(key)
    if cached is not None:
        return cached

    deck = [{"_kind": "land"} for _ in range(land_count)] + list(nonlands)
    commander_cmc = max(1, int(math.ceil(get_cmc(commander))))
    commander_colors = count_pips(commander.get("mana_cost") or "")
    commander_color_req = sum(1 for c, n in commander_colors.items() if n > 0)
    synergy_pairs = [(a, b) for a, b in SYNERGY_PAIRS if a not in AMBIENT_TAGS and b not in AMBIENT_TAGS]
    plan_profile = plan_profile or infer_commander_plan(commander)
    package_profile = choose_active_packages(plan_profile, nonlands, tag_index)
    required_tags: dict[str, int] = dict(plan_profile.get("required_tags", {}))
    primary_plan = package_profile.get("primary_plan")
    if primary_plan in PLAN_ENGINE_RULES:
        finisher_tags: frozenset[str] = frozenset(PLAN_ENGINE_RULES[primary_plan]["closure_tags"])
    else:
        finisher_tags = frozenset(plan_profile.get("finisher_tags", frozenset({"wincon"})))

    dead_hands = 0
    total_mana_spent = 0.0
    total_first_play = 0.0
    on_curve = 0
    pair_assembled = 0
    engine_complete = 0
    finisher_seen = 0

    for _ in range(trials):
        sample = random.sample(deck, min(len(deck), 13))
        hand = sample[:7]
        draws = sample[7:]
        lands_in_hand = sum(1 for c in hand if c.get("_kind") == "land")
        if lands_in_hand <= 1 or lands_in_hand >= 6:
            hand = sample[:6]
            draws = sample[6:12]

        lands_in_play = 0
        future_ramp = 0
        mana_spent = 0
        first_play_turn = 7
        seen_tags: Counter = Counter()
        commander_turn = 99

        for turn in range(1, 13):
            if turn > 1 and draws:
                hand.append(draws.pop(0))

            land_idx = next((i for i, c in enumerate(hand) if c.get("_kind") == "land"), None)
            if land_idx is not None:
                hand.pop(land_idx)
                lands_in_play += 1

            available_mana = lands_in_play + future_ramp

            castable = [
                c for c in hand
                if c.get("_kind") != "land" and get_cmc(c) <= available_mana
            ]
            castable.sort(key=lambda c: (
                -plan_cast_priority_bonus(c, seen_tags, plan_profile, package_profile, tag_index),
                not is_cheap_ramp_card(c),
                not is_cheap_setup_card(c),
                get_cmc(c),
            ))

            spent_this_turn = 0
            for card in castable:
                cmc = max(0, int(math.ceil(get_cmc(card))))
                if spent_this_turn + cmc > available_mana:
                    continue
                spent_this_turn += cmc
                hand.remove(card)
                for tag in tag_index.get(card["name"], frozenset()):
                    seen_tags[tag] += 1
                if first_play_turn == 7 and cmc > 0:
                    first_play_turn = turn
                if is_cheap_ramp_card(card):
                    future_ramp += 1

            mana_spent += spent_this_turn

            if commander_turn == 99 and available_mana >= commander_cmc and lands_in_play >= commander_color_req:
                commander_turn = turn

        if first_play_turn > 3:
            dead_hands += 1
        total_mana_spent += mana_spent
        total_first_play += first_play_turn
        if commander_turn <= commander_cmc:
            on_curve += 1
        if any(seen_tags[a] > 0 and seen_tags[b] > 0 for a, b in synergy_pairs):
            pair_assembled += 1
        seen_plus_hand = Counter(seen_tags)
        for card in hand:
            for tag in tag_index.get(card["name"], frozenset()):
                seen_plus_hand[tag] += 1
        plan_summary = plan_component_summary(seen_plus_hand, plan_profile, package_profile)
        components = plan_summary["components"]
        if components and all(ok for _label, _have, _need, ok in components) and plan_summary["closure_hits"] > 0:
            engine_complete += 1
        elif not components and required_tags and all(seen_tags.get(tag, 0) >= count for tag, count in required_tags.items()):
            engine_complete += 1
        if any(seen_tags.get(tag, 0) > 0 for tag in finisher_tags):
            finisher_seen += 1

    result = {
        "dead_hand_rate": dead_hands / trials,
        "mean_mana_spent": total_mana_spent / trials,
        "mean_first_play_turn": total_first_play / trials,
        "commander_on_curve_rate": on_curve / trials,
        "pair_assembly_rate": pair_assembled / trials,
        "engine_completion_rate": engine_complete / trials,
        "finisher_seen_rate": finisher_seen / trials,
    }
    _GOLDFISH_CACHE[key] = result
    return result


AMBIENT_TAGS: frozenset[str] = frozenset({
    "tribal", "historic_spell", "modified_enabler", "spirit_spell",
})


def is_reportable_synergy(tag: str, count: int, flat_tags: Counter) -> bool:
    if count < 3:
        return False
    if tag == "historic_spell":
        return count >= 6 and flat_tags.get("historic_payoff", 0) >= 2
    if tag == "modified_enabler":
        return count >= 5 and flat_tags.get("modified_payoff", 0) >= 2
    if tag == "equipment":
        return count >= 4 and (
            flat_tags.get("equipment_payoff", 0) >= 2
            or flat_tags.get("voltron_payoff", 0) >= 2
        )
    if tag == "spirit_spell":
        return count >= 6 and flat_tags.get("spiritcraft_payoff", 0) >= 2
    if tag == "tribal":
        return count >= 5
    if tag in AMBIENT_TAGS:
        return False
    return True


def synergy_added_by_card(
    card_name: str,
    deck_names: list[str],
    db: dict,
    tag_index: dict[str, frozenset[str]],
) -> float:
    """How much synergy does adding card_name contribute to the existing deck?"""
    if not deck_names:
        return 0.0

    card_tags = tag_index.get(card_name, frozenset())
    card_subtypes = get_subtypes(db.get(card_name, {}))
    score = 0.0

    deck_tribe_counts: Counter = Counter()
    for existing_name in deck_names:
        for sub in get_subtypes(db.get(existing_name, {})):
            deck_tribe_counts[sub] += 1

    for existing_name in deck_names:
        ex_tags = tag_index.get(existing_name, frozenset())
        ex_subtypes = get_subtypes(db.get(existing_name, {}))

        # Tribal: shared creature types
        shared_tribes = card_subtypes & ex_subtypes
        # Only reward tribe overlap when that tribe already has meaningful density.
        # This prevents incidental shared subtypes from steering non-tribal decks.
        for sub in shared_tribes:
            if deck_tribe_counts.get(sub, 0) >= 5:
                score += 0.25

        # Synergy pairs
        for tag_a, tag_b in SYNERGY_PAIRS:
            if (tag_a in card_tags and tag_b in ex_tags) or \
               (tag_b in card_tags and tag_a in ex_tags):
                score += 0.6

        # Shared synergy categories (soft bonus)
        shared = card_tags & ex_tags
        score += len(shared) * 0.05

    # Combo piece pull: bonus for cards that partially assemble a known combo
    score += combo_synergy_bonus(card_name, deck_names)

    return score / max(len(deck_names), 1)


def deck_synergy_total(
    deck_names: list[str],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    plan_profile: dict[str, object] | None = None,
) -> float:
    """Aggregate synergy score for an entire deck."""
    flat_tags: Counter = Counter()
    for name in deck_names:
        for tag in tag_index.get(name, frozenset()):
            flat_tags[tag] += 1

    tribe_counter: Counter = Counter()
    for name in deck_names:
        for sub in get_subtypes(db.get(name, {})):
            tribe_counter[sub] += 1

    plans = frozenset((plan_profile or {}).get("plans", frozenset()))
    tribal_enabled = "tribal_synergy" in plans
    primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    deck_cards = [db.get(name, {}) for name in deck_names if name in db]
    tribal_alignment = _tribal_alignment_ratio(primary_tribe, list(plans), deck_cards, tag_index)
    if tribal_enabled:
        tribal_scale = 0.40 + 0.60 * max(0.0, min(1.0, tribal_alignment))
        tribe_score = sum(
            math.log(max(cnt, 1)) * 0.8 * tribal_scale
            for _sub, cnt in tribe_counter.items()
            if cnt >= 6
        )
        if tribe_counter:
            top_tribe_count = tribe_counter.most_common(1)[0][1]
            if top_tribe_count >= 20:
                tribe_score += 6.0 * tribal_scale
            elif top_tribe_count >= 15:
                tribe_score += 3.5 * tribal_scale
            elif top_tribe_count >= 10:
                tribe_score += 1.5 * tribal_scale
    else:
        # Tiny residual signal for natural subtype concentration, but not enough
        # to drag non-tribal decks toward low-impact tribe filler.
        tribe_score = sum(
            math.log(max(cnt, 1)) * 0.18
            for _sub, cnt in tribe_counter.items()
            if cnt >= 7
        )

    pair_score = 0.0
    for tag_a, tag_b in SYNERGY_PAIRS:
        n_a = flat_tags.get(tag_a, 0)
        n_b = flat_tags.get(tag_b, 0)
        if n_a > 0 and n_b > 0:
            pair_score += math.sqrt(n_a * n_b) * 0.4

    # Bonus for deep counter synergy
    if flat_tags.get("counters", 0) >= 8:
        pair_score += 3.0
    # Bonus for deep token go-wide
    if flat_tags.get("token_maker", 0) >= 6 and flat_tags.get("anthem", 0) >= 2:
        pair_score += 3.0

    # Engine completeness bonuses
    if flat_tags.get("graveyard_enabler", 0) >= 6 and \
            flat_tags.get("graveyard_payoff", 0) >= 5 and \
            flat_tags.get("sacrifice", 0) >= 3:
        pair_score += 4.0
    if flat_tags.get("etb_trigger", 0) >= 7 and flat_tags.get("blink_enabler", 0) >= 3:
        pair_score += 3.0
    if flat_tags.get("death_trigger", 0) >= 4 and flat_tags.get("sacrifice", 0) >= 4:
        pair_score += 3.0

    # Graveyard engine: require self_mill specifically (not just discard)
    if flat_tags.get("self_mill", 0) >= 4 and \
            flat_tags.get("graveyard_payoff", 0) >= 5 and \
            flat_tags.get("sac_outlet", 0) >= 2:
        pair_score += 4.5

    # Combat damage engine completeness
    if flat_tags.get("evasion", 0) >= 8 and flat_tags.get("combat_damage_trigger", 0) >= 2:
        pair_score += 3.5

    # Exile-zone play engine completeness
    if flat_tags.get("exile_enabler", 0) >= 5 and flat_tags.get("cast_from_exile", 0) >= 3:
        pair_score += 3.5

    # Spell cost engine completeness
    if flat_tags.get("cost_reduction", 0) >= 3 and flat_tags.get("spells_enabler", 0) >= 10:
        pair_score += 3.5

    # Voltron engine completeness
    if flat_tags.get("voltron_enabler", 0) >= 8 and flat_tags.get("evasion", 0) >= 4:
        pair_score += 3.0

    # Lands engine completeness
    if flat_tags.get("extra_land_drop", 0) >= 4 and flat_tags.get("landfall", 0) >= 5:
        pair_score += 3.5

    pair_score += _narrow_mechanic_adjustment(flat_tags)

    # Known combo completeness bonus — large reward for assembling full combos
    pair_score += combo_completeness_bonus(deck_names)

    return tribe_score + pair_score


# ─────────────────────────────────────────────────────────────────────────────
# POWER LEVEL SCORING
# Based on the vanilla test, keyword values, oracle text patterns, and rarity.
# ─────────────────────────────────────────────────────────────────────────────

_DRAW_VALUE_RE = re.compile(r"draw (?:two|three|four|x) cards?")

KEYWORD_BONUS: dict[str, float] = {
    "flying":        0.75,
    "haste":         1.00,
    "hexproof":      1.50,
    "shroud":        1.00,
    "deathtouch":    0.75,
    "lifelink":      0.50,
    "flash":         0.75,
    "double strike": 1.50,
    "first strike":  0.50,
    "indestructible":1.50,
    "trample":       0.50,
    "vigilance":     0.35,
    "menace":        0.35,
    "prowess":       0.75,
    "ward":          0.75,
    "reach":         0.25,
}

RARITY_BONUS: dict[str, float] = {
    "common":   0.00,
    "uncommon": 0.25,
    "rare":     0.75,
    "mythic":   1.50,
}


def score_power(card: dict) -> float:
    """Score a card's raw constructed power level on [0, 10]."""
    cmc = get_cmc(card)
    oracle = (card.get("oracle_text") or "").lower()
    keywords = [k.lower() for k in (card.get("keywords") or [])]
    type_line = card.get("type_line") or ""
    power = get_power(card)
    toughness = get_toughness(card)
    rarity = card.get("rarity") or "common"

    if is_land(card):
        score = 5.0
        if "enters tapped" in oracle and "pay 2 life" not in oracle and "unless" not in oracle:
            score -= 1.5
        produced = card.get("produced_mana") or []
        if len([m for m in produced if m != "C"]) >= 2:
            score += 2.0
        if re.search(r"search your library for a (?:basic )?land", oracle):
            score += 1.5
        return min(10.0, score)

    score = 5.0

    # Stat efficiency vs vanilla baseline
    if is_creature(card) and cmc > 0:
        expected = cmc * 2
        actual = power + toughness
        ratio = actual / max(expected, 1)
        score += (ratio - 1.0) * 2.5

    # Premium aggressive bodies (don't reward Defender — it can't attack by default)
    has_defender = "defender" in [k.lower() for k in (card.get("keywords") or [])]
    if not has_defender:
        if cmc == 1 and is_creature(card) and power >= 2:
            score += 2.0
        if cmc == 2 and is_creature(card) and power >= 3:
            score += 1.5
        if cmc == 3 and is_creature(card) and power >= 4:
            score += 1.0
    else:
        score -= 1.0  # Defender penalty: can never attack without external help

    # Keyword bonuses
    for kw, val in KEYWORD_BONUS.items():
        if kw in keywords:
            score += val

    # Card advantage
    if "draw a card" in oracle:
        score += 1.5
    if _DRAW_VALUE_RE.search(oracle):
        score += 2.5
    if "search your library for" in oracle and "land" not in oracle:
        score += 1.5
    if "create" in oracle and "token" in oracle:
        score += 0.75
    if "from your graveyard" in oracle and "return" in oracle:
        score += 1.0

    # Efficient removal
    if re.search(r"destroy target|exile target", oracle):
        if cmc <= 2:
            score += 1.5
        elif cmc <= 3:
            score += 0.75

    # Efficient counterspells
    if "counter target spell" in oracle:
        if cmc <= 2:
            score += 1.5
        elif cmc <= 3:
            score += 0.75

    # Sweepers — exclude "then destroy all X if [condition]" (secondary triggered
    # effects gated on combo conditions, e.g. Amalia Benavides Aguirre)
    if re.search(r"destroy all|exile all creatures|all creatures get -(?:\d+|x)|return all .{0,20}permanents", oracle) and \
            not re.search(r"\bthen destroy all .{0,80}\bif\b", oracle):
        score += 1.0 if cmc <= 5 else 0.5

    # Planeswalker premium
    if "Planeswalker" in type_line:
        score += 1.5

    # Penalties
    if "enters tapped" in oracle:
        score -= 0.5
    if cmc >= 6:
        score -= (cmc - 5) * 0.4
    if cmc >= 8:
        score -= 2.0

    # Change 4: stronger opponent-helps penalties
    if re.search(r"target opponent (creates?|puts?|draws?|gains?)", oracle):
        score -= 3.5
    if re.search(r"each opponent (creates?|draws?|gains? \d+ life)", oracle):
        score -= 2.5
    if re.search(r"\beach opponent(?:s)? draws\b", oracle):
        score -= 3.0
    if re.search(r"(opponent|opponents) (?:may |also )?(?:draw|search|tutor)", oracle):
        score -= 2.5
    if re.search(r"(you and|both) (?:your )?opponents?", oracle):
        score -= 1.5

    # Treat unknown rarities (e.g. "special") as "rare"
    score += RARITY_BONUS.get(rarity, RARITY_BONUS["rare"])

    # Change 5: blend in constructed-playability heuristic
    score += score_constructed_playability(card) * 0.5

    return max(0.0, min(10.0, score))


# ─────────────────────────────────────────────────────────────────────────────
# ARCHETYPE FIT SCORING
# ─────────────────────────────────────────────────────────────────────────────

def score_archetype_fit(card: dict, archetype: str, roles: list[str]) -> float:
    """Score how well a card fits the archetype on [0, 1]."""
    if is_land(card):
        return 1.0

    cfg = ARCHETYPE_CONFIG[archetype]
    cmc = get_cmc(card)
    oracle = (card.get("oracle_text") or "").lower()
    keywords = [k.lower() for k in (card.get("keywords") or [])]
    type_line = card.get("type_line") or ""

    # CMC fit: fraction of curve target at this CMC
    cmc_int = min(int(cmc), 6)
    curve_total = max(sum(cfg["curve_targets"].values()), 1)
    cmc_fit = cfg["curve_targets"].get(cmc_int, 0) / curve_total

    # Role fit: best role alignment
    role_ratios = cfg["role_ratios"]
    role_fit = max((role_ratios.get(r, 0) for r in roles), default=0.05)

    # Archetype-specific bonuses/penalties
    bonus = 0.0
    if archetype == "aggro":
        if cmc <= 2 and "threat" in roles:
            bonus += 0.30
        if "haste" in keywords:
            bonus += 0.20
        if "flying" in keywords and "threat" in roles:
            bonus += 0.10
        if cmc >= 5:
            bonus -= 0.50  # aggro hates high-CMC cards

    elif archetype == "midrange":
        if cmc in (2, 3, 4) and "threat" in roles:
            bonus += 0.20
        if is_creature(card) and "draw" in roles:
            bonus += 0.20  # ETB value creatures
        if "Planeswalker" in type_line:
            bonus += 0.30

    elif archetype == "control":
        if "counterspell" in roles:
            bonus += 0.30
        if "sweeper" in roles:
            bonus += 0.35
        if "draw" in roles and not is_creature(card):
            bonus += 0.25
        if "removal" in roles and cmc <= 3:
            bonus += 0.20
        # Control wants few small creatures
        if is_creature(card) and cmc <= 3 and "threat" in roles and "draw" not in roles:
            bonus -= 0.25
        if is_creature(card) and cmc <= 2 and "threat" in roles:
            bonus -= 0.30

    elif archetype == "combo":
        if "draw" in roles:
            bonus += 0.30
        if "tutor" in roles:
            bonus += 0.45
        if "ramp" in roles:
            bonus += 0.30
        if cmc >= 6 and "wincon" not in roles:
            bonus -= 0.30
        if not is_creature(card) and not is_land(card) and cmc <= 2:
            bonus += 0.25

    return max(0.0, min(1.0, cmc_fit * 0.35 + role_fit * 0.45 + bonus * 0.20))


def archetype_blend_multiplier(
    roles: list[str],
    archetype: str,
    role_counts: Counter,
    selection_size: int,
    nonland_slots: int,
) -> float:
    """
    Scale archetype fit based on the current deck shape.

    Early picks stay neutral. Once a shell exists, cards that reinforce the
    deck's dominant role cluster get rewarded, while cards that pull toward a
    weakly represented cluster get a mild penalty unless they help close an
    archetype-role deficit.
    """
    if selection_size < 8 or not roles:
        return 1.0

    clusters = ARCHETYPE_ROLE_CLUSTERS.get(archetype, ())
    if not clusters:
        return 1.0

    cluster_scores = {
        name: sum(int(role_counts.get(role, 0)) for role in cluster_roles)
        for name, cluster_roles in clusters
    }
    dominant_score = max(cluster_scores.values(), default=0)
    if dominant_score <= 0:
        return 1.0

    matching_scores = [
        cluster_scores[name]
        for name, cluster_roles in clusters
        if set(roles) & cluster_roles
    ]
    if not matching_scores:
        return 1.0

    card_cluster_score = max(matching_scores)
    avg_cluster_score = sum(cluster_scores.values()) / max(len(cluster_scores), 1)
    fill_ratio = min(1.0, selection_size / max(nonland_slots, 1))
    coherence = (card_cluster_score - avg_cluster_score) / max(dominant_score, 1)
    multiplier = 1.0 + coherence * (0.14 + 0.10 * fill_ratio)

    role_targets = {
        role: max(1, round(nonland_slots * ratio))
        for role, ratio in ARCHETYPE_CONFIG[archetype]["role_ratios"].items()
    }
    deficit_relief = max(
        (
            role_targets.get(role, 0) - int(role_counts.get(role, 0))
        ) / max(role_targets.get(role, 1), 1)
        for role in roles
    )
    if deficit_relief > 0:
        multiplier += min(0.10, deficit_relief * 0.10)

    return max(0.88, min(1.22, multiplier))


def archetype_coherence_score(cards: list[dict], archetype: str) -> float:
    """Return a normalized score for how concentrated the deck is in archetype role clusters."""
    clusters = ARCHETYPE_ROLE_CLUSTERS.get(archetype, ())
    if not clusters or not cards:
        return 1.0

    cluster_hits: Counter = Counter()
    covered_cards = 0
    for card in cards:
        roles = set(classify_roles(card))
        matched = False
        for name, cluster_roles in clusters:
            if roles & cluster_roles:
                cluster_hits[name] += 1
                matched = True
        if matched:
            covered_cards += 1

    if covered_cards <= 0:
        return 1.0

    dominant = max(cluster_hits.values(), default=0) / covered_cards
    support = sum(cluster_hits.values()) / max(covered_cards, 1)
    return max(0.0, min(1.0, dominant * 0.75 + min(1.0, support / 1.8) * 0.25))


def strategy_coherence_metrics(cards: list[dict], matchers: list[tuple]) -> dict[str, float]:
    """Return coverage and concentration metrics for user strategy alignment."""
    if not cards or not matchers:
        return {
            "match_rate": 0.0,
            "coherence": 0.0,
            "off_strategy_rate": 1.0,
            "intersection_rate": 0.0,
        }

    group_counts: Counter = Counter()
    matched_cards = 0
    off_strategy_cards = 0
    intersection_cards = 0

    for card in cards:
        groups = strategy_match_groups(card, matchers)
        if groups:
            matched_cards += 1
            if len(groups) >= 2:
                intersection_cards += 1
            for group in groups:
                group_counts[group] += 1
        else:
            off_strategy_cards += 1

    if not group_counts:
        return {
            "match_rate": 0.0,
            "coherence": 0.0,
            "off_strategy_rate": 1.0,
            "intersection_rate": 0.0,
        }

    total_group_hits = sum(group_counts.values())
    dominant_ratio = max(group_counts.values()) / max(total_group_hits, 1)
    concentration = sum((count / total_group_hits) ** 2 for count in group_counts.values())
    baseline = 1.0 / max(len(group_counts), 1)
    coherence = 1.0 if len(group_counts) == 1 else (concentration - baseline) / max(1e-9, 1.0 - baseline)

    return {
        "match_rate": matched_cards / max(len(cards), 1),
        "coherence": max(0.0, min(1.0, coherence * 0.65 + dominant_ratio * 0.35)),
        "off_strategy_rate": off_strategy_cards / max(len(cards), 1),
        "intersection_rate": intersection_cards / max(len(cards), 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ARCHETYPE STRUCTURE VALIDATION
# Hard deck-level expectations used by selection and evolutionary refinement.
# These are stricter than ARCHETYPE_CONFIG role ratios: decks can still vary,
# but they should not be accepted if they miss the basic structural skeleton
# of their archetype.
# ─────────────────────────────────────────────────────────────────────────────

# ── Change 6: Infrastructure slot reservations ──────────────────────────────
# Phase -1 guarantees these cards are always attempted before Phase 0.
# Each entry: (role_or_tag, n_slots, cmc_max, filter_fn_name_or_None)
# role_or_tag : matched against classify_roles(card) or tag_index[card]
# n_slots     : maximum number of cards to pull in Phase -1
# cmc_max     : only cards with cmc <= this value qualify (None = no cap)
INFRASTRUCTURE_SLOTS: list[tuple[str, int, int | None]] = [
    ("ramp",        8,  4),   # mana ramp, keep curves low
    ("draw",        6,  5),   # card draw
    ("removal",     5,  4),   # targeted removal
    ("sweeper",     2,  6),   # board wipes
    ("counterspell",3,  3),   # counterspells
    ("tutor",       2,  5),   # tutors
]


ARCHETYPE_HARD_RULES: dict[str, dict[str, object]] = {
    "aggro": {
        "min_roles": {"threat": 18, "removal": 3, "draw": 4, "ramp": 6},
        "min_low_cmc_threats": 12,
        "max_avg_cmc": 2.85,
        "max_sweepers": 1,
        "min_win_paths": 1,
    },
    "midrange": {
        "min_roles": {"threat": 12, "removal": 5, "draw": 5, "ramp": 7},
        "min_low_cmc_threats": 6,
        "max_avg_cmc": 3.55,
        "min_sweepers": 1,
        "min_win_paths": 1,
    },
    "control": {
        "min_roles": {"removal": 8, "sweeper": 3, "draw": 7, "counterspell": 5, "ramp": 6},
        "max_creatures": 14,
        "max_low_cmc_threats": 5,
        "max_avg_cmc": 3.75,
        "min_win_paths": 1,
    },
    "combo": {
        "min_roles": {"draw": 8, "ramp": 8, "tutor": 4},
        "max_avg_cmc": 3.45,
        "max_high_cmc_nonwincon": 8,
        "min_win_paths": 1,
    },
}


def _is_repeatable_draw(card: dict) -> bool:
    oracle = (card.get("oracle_text") or "").lower()
    type_line = (card.get("type_line") or "")
    return (
        "whenever you draw" in oracle
        or "whenever" in oracle and "draw" in oracle
        or "at the beginning" in oracle and "draw" in oracle
        or "planeswalker" in type_line.lower() and "draw" in oracle
    )


def evaluate_archetype_structure(
    cards: list[dict],
    tag_index: dict[str, frozenset[str]],
    archetype: str,
) -> dict[str, object]:
    """Evaluate whether a completed nonland suite satisfies archetype minimums."""
    rules = ARCHETYPE_HARD_RULES.get(archetype, {})
    role_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    low_cmc_threats = 0
    creature_count = 0
    sweepers = 0
    repeatable_draw = 0
    high_cmc_nonwincon = 0

    for card in cards:
        roles = set(classify_roles(card))
        role_counts.update(roles)
        tag_counts.update(tag_index.get(card["name"], frozenset()))
        if is_creature(card):
            creature_count += 1
        if "threat" in roles and get_cmc(card) <= 3:
            low_cmc_threats += 1
        if "sweeper" in roles:
            sweepers += 1
        if "draw" in roles and _is_repeatable_draw(card):
            repeatable_draw += 1
        if get_cmc(card) >= 6 and "wincon" not in roles:
            high_cmc_nonwincon += 1

    avg_cmc = sum(get_cmc(c) for c in cards) / max(len(cards), 1)
    win_paths = sum(1 for w in detect_win_conditions([c["name"] for c in cards], tag_counts) if w["available"])

    penalty = 0.0
    hard_fail = False
    needed_roles: set[str] = set()
    findings: list[str] = []

    for role, need in dict(rules.get("min_roles", {})).items():
        have = role_counts.get(role, 0)
        if have < need:
            missing = need - have
            needed_roles.add(role)
            penalty += missing * (0.80 if role in {"removal", "draw", "counterspell", "ramp"} else 0.55)
            findings.append(f"{role} {have}/{need}")
            if role in {"removal", "draw", "counterspell", "ramp"} and missing >= max(2, need // 3):
                hard_fail = True

    max_avg_cmc = rules.get("max_avg_cmc")
    if isinstance(max_avg_cmc, (int, float)) and avg_cmc > float(max_avg_cmc):
        overflow = avg_cmc - float(max_avg_cmc)
        penalty += overflow * 6.0
        findings.append(f"avg_cmc {avg_cmc:.2f}>{float(max_avg_cmc):.2f}")
        if overflow >= 0.40:
            hard_fail = True

    min_low = rules.get("min_low_cmc_threats")
    if isinstance(min_low, int) and low_cmc_threats < min_low:
        missing = min_low - low_cmc_threats
        needed_roles.add("threat")
        penalty += missing * 0.60
        findings.append(f"cheap_threats {low_cmc_threats}/{min_low}")
        if missing >= max(3, min_low // 3):
            hard_fail = True

    max_low = rules.get("max_low_cmc_threats")
    if isinstance(max_low, int) and low_cmc_threats > max_low:
        penalty += (low_cmc_threats - max_low) * 0.55
        findings.append(f"cheap_threats {low_cmc_threats}>{max_low}")

    min_sweepers = rules.get("min_sweepers")
    if isinstance(min_sweepers, int) and sweepers < min_sweepers:
        needed_roles.add("sweeper")
        penalty += (min_sweepers - sweepers) * 1.0
        findings.append(f"sweepers {sweepers}/{min_sweepers}")

    max_sweepers = rules.get("max_sweepers")
    if isinstance(max_sweepers, int) and sweepers > max_sweepers:
        penalty += (sweepers - max_sweepers) * 0.80
        findings.append(f"sweepers {sweepers}>{max_sweepers}")

    max_creatures = rules.get("max_creatures")
    if isinstance(max_creatures, int) and creature_count > max_creatures:
        penalty += (creature_count - max_creatures) * 0.50
        findings.append(f"creatures {creature_count}>{max_creatures}")
        if creature_count - max_creatures >= 5:
            hard_fail = True

    max_high_cmc_nonwincon = rules.get("max_high_cmc_nonwincon")
    if isinstance(max_high_cmc_nonwincon, int) and high_cmc_nonwincon > max_high_cmc_nonwincon:
        penalty += (high_cmc_nonwincon - max_high_cmc_nonwincon) * 0.65
        findings.append(f"expensive_nonfinishers {high_cmc_nonwincon}>{max_high_cmc_nonwincon}")

    min_win_paths = int(rules.get("min_win_paths", 0))
    if win_paths < min_win_paths:
        penalty += (min_win_paths - win_paths) * 2.5
        findings.append(f"win_paths {win_paths}/{min_win_paths}")
        if win_paths == 0:
            hard_fail = True

    if role_counts.get("draw", 0) > 0 and repeatable_draw == 0 and archetype in {"midrange", "control", "combo"}:
        penalty += 1.2
        findings.append("repeatable_draw 0")

    return {
        "penalty": penalty,
        "hard_fail": hard_fail,
        "needed_roles": frozenset(needed_roles),
        "findings": tuple(findings),
        "avg_cmc": avg_cmc,
        "role_counts": role_counts,
        "tag_counts": tag_counts,
        "win_paths": win_paths,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CARD SELECTION — CONSTRAINT-GREEDY
# ─────────────────────────────────────────────────────────────────────────────

RARITY_ORDER = ["common", "uncommon", "rare", "mythic"]


def select_nonlands(
    card_pool: list[dict],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    archetype: str,
    colors: set[str],
    strategy_hint: str,
    nonland_slots: int,
    max_rarity: str,
    diversity: float = 1.0,
    commander: dict | None = None,
    plan_profile: dict[str, object] | None = None,
    strict_tribal: bool = False,
    ignore_tribal: bool = False,
) -> list[dict]:
    """
    Curve-first card selection with role weighting and synergy awareness.

    Algorithm:
      1. For each CMC bucket defined in curve_targets, fill the target number
         of card slots by ranking candidates at that CMC by a composite score
         (power × archetype-fit × role-fit × strategy-match).
      2. Within each CMC bucket, prefer 4-of copies of elite cards and 2-of
         copies of role-players, respecting the 4-copy limit and legend rule.
      3. Any remaining slots are backfilled from the highest-scoring cards
         across all CMC values.
    """
    max_rarity_idx = RARITY_ORDER.index(max_rarity) if max_rarity in RARITY_ORDER else 3
    cfg = ARCHETYPE_CONFIG[archetype]
    plan_profile = plan_profile or infer_commander_plan(commander)
    required_tags: dict[str, int] = dict(plan_profile.get("required_tags", {}))
    finisher_tags: frozenset[str] = frozenset(plan_profile.get("finisher_tags", frozenset({"wincon"})))
    primary_tribe: str | None = plan_profile.get("primary_tribe")
    active_plans: frozenset[str] = frozenset(plan_profile.get("plans", frozenset()))
    priority_profile = derive_priority_profile(plan_profile)
    core_tags: frozenset[str] = frozenset(priority_profile.get("core_tags", frozenset()))
    support_tags: frozenset[str] = frozenset(priority_profile.get("support_tags", frozenset()))
    redundancy_targets: dict[str, int] = dict(priority_profile.get("redundancy_targets", {}))

    # ── Strict tribal: raise tribe density target and penalize non-tribe creatures ──
    if strict_tribal and primary_tribe:
        tribe_tag = f"tribe_{primary_tribe}"
        redundancy_targets[tribe_tag] = max(redundancy_targets.get(tribe_tag, 0), 30)

    # ── Merge user strategy with commander auto-strategy ──────────────────────
    auto_strat = commander_auto_strategy(commander, ignore_tribal=ignore_tribal) if commander else ""
    combined_hint = f"{strategy_hint} {auto_strat}".strip()
    strategy_words = set(extract_strategy_terms(combined_hint)) if combined_hint else set()

    # ── Exclude the commander itself from the main deck ───────────────────────
    commander_name = commander.get("name") if commander else None

    # ── Rarity filter ─────────────────────────────────────────────────────────
    def rarity_idx(card: dict) -> int:
        r = card.get("rarity") or "common"
        return RARITY_ORDER.index(r) if r in RARITY_ORDER else 2

    filtered = [
        c for c in card_pool
        if rarity_idx(c) <= max_rarity_idx
        and c.get("name") != commander_name   # commander lives in command zone
    ]

    # ── Strict tribal: hard-filter non-tribe creatures out of the pool ────────
    # Penalties alone can't prevent non-tribe creatures from sneaking in during
    # role-fill and backfill when tribe options run out. Removing them from the
    # pool entirely is the only reliable guarantee. Non-creature cards (ramp,
    # draw, removal, enchantments, artifacts) are always kept.
    if strict_tribal and primary_tribe:
        _tribe_tag = f"tribe_{primary_tribe}"
        filtered = [
            c for c in filtered
            if "Creature" not in (c.get("type_line") or "")
            or _tribe_tag in tag_index.get(c.get("name", ""), frozenset())
        ]

    _pool_slot_baseline = _slot_mix_from_cards(filtered)
    _pool_tag_slot_affinity = _build_tag_slot_affinity(filtered, tag_index, _pool_slot_baseline)

    package_profile = choose_active_packages(plan_profile, filtered, tag_index)
    allowed_package_tags: frozenset[str] = frozenset(package_profile.get("allowed_tags", frozenset()))
    discouraged_package_tags: frozenset[str] = frozenset(package_profile.get("discouraged_tags", frozenset()))
    _tribal_alignment = float(package_profile.get("tribal_alignment", 1.0))
    if (not strict_tribal) and primary_tribe and "tribal_synergy" in active_plans:
        _tribe_tag_runtime = f"tribe_{primary_tribe}"
        _base_target = int(redundancy_targets.get(_tribe_tag_runtime, 0))
        if _base_target > 0:
            _scaled_target = _scaled_tribal_target(_base_target, _tribal_alignment, active_plans)
            redundancy_targets[_tribe_tag_runtime] = min(_base_target, _scaled_target)
    _tribal_tension = (
        not strict_tribal
        and primary_tribe is not None
        and "tribal_synergy" in active_plans
        and len(active_plans) > 1
    )
    _tribe_tag = f"tribe_{primary_tribe}" if primary_tribe else ""
    _nontribal_core_tags: frozenset[str] = frozenset(
        t for t in core_tags if not t.startswith("tribe_")
    )
    _nontribal_support_tags: frozenset[str] = frozenset(
        t for t in support_tags if not t.startswith("tribe_")
    )
    _nontribal_finisher_tags: frozenset[str] = frozenset(
        t for t in finisher_tags if not t.startswith("tribe_")
    )
    _nontribal_plan_tags: frozenset[str] = (
        _nontribal_core_tags | _nontribal_support_tags | _nontribal_finisher_tags
    )

    # ── Strategy bonus ────────────────────────────────────────────────────────
    _strat_matchers = build_strategy_matchers(strategy_words) if strategy_words else []

    def strat_bonus(card: dict) -> float:
        if not _strat_matchers:
            return 0.0
        type_line = card.get("type_line") or ""
        oracle = card.get("oracle_text") or ""
        name = card.get("name") or ""
        matched_groups = strategy_match_groups(card, _strat_matchers)
        base = 0.0
        for type_pat, oracle_pats, _w, _orig_words in _strat_matchers:
            if type_pat and type_pat.search(type_line):
                base += 3.0
            elif any(p.search(oracle) for p in oracle_pats):
                base += 1.5
            elif type_pat and type_pat.search(name):
                base += 0.5
        # Coherence multiplier: a card satisfying N distinct user-entered keywords
        # scores geometrically higher, pulling intersection cards strongly to the top.
        # 1 keyword → 1.0x  |  2 → 1.7x  |  3 → 2.4x  |  4 → 3.1x
        n = len(matched_groups)
        if n >= 2:
            base *= 1.0 + 0.7 * (n - 1)
        return base

    # ── Composite score ───────────────────────────────────────────────────────
    def composite(card: dict) -> float:
        roles = classify_roles(card)
        pw = score_power(card)
        af = score_archetype_fit(card, archetype, roles)
        sb = strat_bonus(card)

        card_oracle = (card.get("oracle_text") or "").lower()

        # ── Structural penalties applied at composite level ───────────────────
        # These compete directly with strategy bonuses rather than being diluted
        # by the 0.30 weight applied to score_power.
        struct_pen = 0.0

        # Conditional activation: card ability requires external pump/setup
        if re.search(r"activate only if .{0,80}(power|toughness) is [3-9]\d* or greater", card_oracle):
            struct_pen -= 3.5  # e.g. Bloodshot Trainee: useless at base power
        if re.search(r"activate only if you control \d+ or more", card_oracle):
            struct_pen -= 1.5
        if re.search(r"activate only if you have \d+ or more life", card_oracle):
            struct_pen -= 1.0

        # Conditional combat restriction: ongoing support required to attack/block
        if re.search(r"can't (attack|block) (or block |or attack )?unless (you.ve |you have )", card_oracle):
            struct_pen -= 2.0

        # Hard DFC flip conditions: back face is effectively unreachable
        if re.search(r"if an opponent drew (four|five|six|seven|\d+) or more cards this turn", card_oracle):
            struct_pen -= 3.5  # Behold the Unspeakable
        if re.search(r"if you.ve drawn (seven|eight|nine|ten|\d+) or more cards", card_oracle):
            struct_pen -= 2.5  # The Modern Age

        # Change 1: penalise cards whose named dependencies are absent from pool
        card_tags = tag_index.get(card.get("name", ""), frozenset())
        _named_deps = extract_named_dependencies(card)
        if _named_deps:
            _missing_deps = _named_deps - _pool_names
            # Each missing named dependency subtracts up to 1.5 (capped at 3.0 total)
            struct_pen -= min(3.0, len(_missing_deps) * 1.5)

        # Orphaned payoff: payoff tag present but no enablers exist in the pool
        for payoff_tag, enabler_tag in PAYOFF_ENABLER_PAIRS:
            if payoff_tag in card_tags and enabler_tag not in _pool_tags:
                struct_pen -= 2.5

        req_penalty, _unmet = evaluate_card_requirements(
            card, _pool_deck_state, format_name="commander"
        )
        struct_pen -= req_penalty
        struct_pen += _narrow_mechanic_adjustment(_pool_tag_counts, card_tags)
        struct_pen += _support_rule_adjustment(_pool_tag_counts, card_tags)
        struct_pen -= liability_penalty(card)
        struct_pen -= commander_role_penalty(card)
        for tag, need in required_tags.items():
            if tag in card_tags:
                struct_pen += min(2.0, 0.22 * need)
        # Core tag bonus scaled by how many are needed: higher redundancy target
        # → higher pre-selection pressure.  Tribe_elf (need=20) gets ~2.7;
        # token_maker (need=7) gets ~1.5; a target-1 tag gets ~0.8.
        for ct in card_tags & core_tags:
            need_for_tag = redundancy_targets.get(ct, 12)
            struct_pen += 0.7 + min(2.0, 0.10 * need_for_tag)
        struct_pen += 0.65 * len(card_tags & support_tags)
        if card_tags & finisher_tags:
            struct_pen += 1.5
        if allowed_package_tags and card_tags & allowed_package_tags:
            struct_pen += 1.1
        if discouraged_package_tags and card_tags & discouraged_package_tags and not (card_tags & allowed_package_tags):
            struct_pen -= 1.6
        if "graveyard_value" in active_plans and "graveyard_hate" in card_tags:
            struct_pen -= 3.5
        if active_plans & {"spells_velocity", "spell_cost_engine"} and is_creature(card):
            if not (card_tags & frozenset({"spells_payoff", "cost_reduction", "draw", "treasure_maker"})):
                struct_pen -= 1.8

        # (Strict tribal creature filtering is handled by hard pool exclusion
        # above — non-tribe creatures never reach composite() when enabled.)

        # Combo pool pull: if this card is a known combo piece and its partner
        # exists in the candidate pool, give a pre-selection bonus so both pieces
        # tend to land in the deck before evolutionary refinement.
        card_name_for_combo = card.get("name", "")
        if card_name_for_combo in _COMBO_INDEX:
            for _cmb in _COMBO_INDEX[card_name_for_combo]:
                _partners = _cmb["pieces"] - {card_name_for_combo}
                if _partners.issubset(_pool_names):
                    _w = 3.5 if _cmb["type"] == "instant_win" else 2.5
                    struct_pen += _w

        # Change 3: quality gate — low-power cards get diminished strategy bonus
        # so a keyword match on a bad card can't drag it into the deck.
        # pw is on [0, 10]; gate kicks in below 3.0 (clearly weak cards).
        if pw < 3.0:
            sb *= pw / 3.0
        elif pw < 5.0:
            sb *= 0.7 + 0.3 * ((pw - 3.0) / 2.0)

        base = pw * 0.30 + af * 10 * 0.35 + sb + struct_pen
        if diversity > 0:
            base += random.gauss(0, diversity)
        return base

    # Pre-compute which enabler tags exist anywhere in the filtered pool.
    # Used in composite to penalize payoff cards whose enablers are entirely absent.
    _pool_tags: frozenset[str] = frozenset(
        tag
        for c in filtered
        for tag in tag_index.get(c.get("name", ""), frozenset())
    )
    _pool_tag_counts: Counter = _tag_counter_from_cards(filtered, tag_index)
    _pool_deck_state = build_deck_state(
        filtered, tag_index, classify_roles, get_subtypes, commander=commander
    )

    # Pre-compute which combo pieces exist in the pool — used to give pool-level
    # combo pull in composite() before any cards are selected.
    _pool_names: frozenset[str] = frozenset(c.get("name", "") for c in filtered)

    # Pre-score and group by CMC
    # card_by_cmc respects max_cmc so Phase 1 never places over-cost cards;
    # global_scored keeps all cards for Phases 2-3 which filter themselves.
    _max_cmc_phase1 = cfg.get("max_cmc", 8)
    card_by_cmc: dict[int, list[tuple[float, dict]]] = defaultdict(list)
    global_scored: list[tuple[float, dict]] = []
    for card in filtered:
        sc = composite(card)
        cmc_val = get_cmc(card)
        cmc_int = min(int(cmc_val), 6)
        if cmc_val <= _max_cmc_phase1:
            card_by_cmc[cmc_int].append((sc, card))
        global_scored.append((sc, card))

    for cmc_int in card_by_cmc:
        card_by_cmc[cmc_int].sort(key=lambda x: -x[0])
    global_scored.sort(key=lambda x: -x[0])

    # ── Copy count rules — Singleton format ──────────────────────────────────
    def desired_copies(card: dict, sc: float) -> int:
        return 1  # Commander is singleton: one copy of each nonbasic card

    selected_names: list[str] = []
    copy_counts: dict[str, int] = {}
    selected_tag_counts: Counter = Counter()
    selected_subtype_counts: Counter = Counter()
    selected_type_counts: Counter = Counter()
    selected_role_counts: Counter = Counter()
    selected_strategy_counts: Counter = Counter()
    selected_multicolor_creatures = 0
    # Count cards added that touch no core/support/finisher tag — used by the
    # filler-budget escalation inside _selection_need_bonus.
    selected_filler_count = 0

    if commander is not None:
        for tag in tag_index.get(commander["name"], frozenset()):
            selected_tag_counts[tag] += 1
        for subtype in get_subtypes(commander):
            selected_subtype_counts[subtype] += 1
        for type_word in {"artifact", "battle", "creature", "enchantment", "instant", "land", "planeswalker", "sorcery"}:
            if type_word.title() in (commander.get("type_line") or "") or type_word in (commander.get("type_line") or "").lower():
                if type_word in (commander.get("type_line") or "").lower():
                    selected_type_counts[type_word] += 1
        for role in set(classify_roles(commander)):
            selected_role_counts[role] += 1
        if "Creature" in (commander.get("type_line") or "") and len(commander.get("color_identity") or []) >= 2:
            selected_multicolor_creatures += 1

    def _add_selected_card(name: str, copies: int = 1) -> None:
        nonlocal selected_multicolor_creatures, selected_filler_count
        card = db[name]
        selected_names.extend([name] * copies)
        copy_counts[name] = copy_counts.get(name, 0) + copies
        for tag in tag_index.get(name, frozenset()):
            selected_tag_counts[tag] += copies
        for subtype in get_subtypes(card):
            selected_subtype_counts[subtype] += copies
        card_type_line = (card.get("type_line") or "").lower()
        for type_word in ("artifact", "battle", "creature", "enchantment", "instant", "land", "planeswalker", "sorcery"):
            if type_word in card_type_line:
                selected_type_counts[type_word] += copies
        for role in set(classify_roles(card)):
            selected_role_counts[role] += copies
        if _strat_matchers:
            for group in strategy_match_groups(card, _strat_matchers):
                selected_strategy_counts[group] += copies
        if "Creature" in (card.get("type_line") or "") and len(card.get("color_identity") or []) >= 2:
            selected_multicolor_creatures += copies
        if not (tag_index.get(name, frozenset()) & (core_tags | support_tags | finisher_tags)):
            selected_filler_count += copies

    # Extract primary plan name here so _selection_need_bonus can reference it
    # for engine flow critical gap pressure (and Phase 0 pre-fill below).
    _primary_plan = package_profile.get("primary_plan")

    def _selection_need_bonus(card_name: str) -> float:
        card_tags = tag_index.get(card_name, frozenset())
        bonus = 0.0
        card = db[card_name]
        card_roles = classify_roles(card)
        pressure_mix, unmet_tags, unresolved_ratio = _slot_pressure_from_deficits(
            selected_tag_counts,
            required_tags,
            redundancy_targets,
            core_tags,
            _pool_tag_slot_affinity,
            _pool_slot_baseline,
        )
        contributes_unmet = bool(card_tags & unmet_tags)
        current_deck_state = {
            "subtype_counts": selected_subtype_counts,
            "type_counts": selected_type_counts,
            "role_counts": selected_role_counts,
            "tag_counts": selected_tag_counts,
            "keyword_counts": Counter(),
            "multicolor_creatures": selected_multicolor_creatures,
        }
        req_penalty, _unmet = evaluate_card_requirements(
            card, current_deck_state, format_name="commander"
        )
        bonus -= req_penalty * 0.85
        bonus -= commander_role_penalty(card)
        archetype_fit = score_archetype_fit(card, archetype, card_roles)
        archetype_blend = archetype_blend_multiplier(
            card_roles,
            archetype,
            selected_role_counts,
            len(selected_names),
            nonland_slots,
        )
        # Mirror the selection-time archetype contribution (af * 10 * 0.35)
        # so cards that reinforce the current archetype shell get pulled upward
        # and archetype-legal but incoherent cards lose some of their edge.
        bonus += archetype_fit * 3.5 * (archetype_blend - 1.0)
        for tag, need in required_tags.items():
            have = selected_tag_counts.get(tag, 0)
            if have < need and tag in card_tags:
                bonus += (need - have) * 0.65
        for tag, need in redundancy_targets.items():
            have = selected_tag_counts.get(tag, 0)
            if have < need and tag in card_tags:
                scale = 0.9 if tag in core_tags else 0.45
                if tag.startswith("tribe_") and not strict_tribal:
                    # Tribe membership alone is low-signal in multi-plan shells;
                    # prioritize tribe cards that also move non-tribal engine tags.
                    if card_tags & _nontribal_plan_tags:
                        scale *= 0.95
                    else:
                        scale *= 0.24
                bonus += (need - have) * scale
        if len(selected_names) >= max(10, nonland_slots // 2):
            if any(t in card_tags for t in finisher_tags):
                bonus += 1.5
        bonus += _slot_pressure_adjustment(card, contributes_unmet, pressure_mix, unresolved_ratio)
        # Synergy density: a card that touches multiple plan tags simultaneously
        # is worth more than two single-hit cards — reward multiplicative coverage.
        plan_tag_hits = len(card_tags & (core_tags | support_tags))
        if plan_tag_hits >= 2:
            bonus += (plan_tag_hits - 1) * 0.6  # +0.6 / +1.2 / +1.8 …
        if selected_names and not (card_tags & (core_tags | support_tags | finisher_tags)):
            # Off-plan penalty tightens as the plan fills: once the engine is built
            # the deck should be MORE selective, not more permissive.
            # Previous behaviour (softening to −0.3) was the root cause of filler bloat.
            plan_completion = 0.0
            if core_tags and redundancy_targets:
                met = sum(
                    1 for t in core_tags
                    if selected_tag_counts.get(t, 0) >= redundancy_targets.get(t, 1)
                )
                plan_completion = met / max(1, len(core_tags))
            # Scales from −1.2 (plan empty, a little filler is fine early)
            #         to   −2.5 (plan complete, strong pressure against filler)
            base_penalty = 1.2 + plan_completion * 1.3
            # Filler budget escalation: the first ~6 off-plan cards are tolerated;
            # beyond that each additional one raises the penalty progressively.
            _filler_budget = 6
            if selected_filler_count >= _filler_budget:
                overage = selected_filler_count - _filler_budget
                base_penalty += 0.4 + overage * 0.25
            bonus -= base_penalty
        if allowed_package_tags and card_tags & allowed_package_tags:
            bonus += 0.75
        if discouraged_package_tags and card_tags & discouraged_package_tags and not (card_tags & allowed_package_tags):
            bonus -= 1.0
        if _tribal_tension and _tribe_tag and _tribe_tag in card_tags and is_creature(card):
            unmet_nontribal = sum(
                max(0, redundancy_targets.get(t, 0) - selected_tag_counts.get(t, 0))
                for t in _nontribal_core_tags
            )
            contributes_nontribal = bool(card_tags & _nontribal_core_tags)
            contributes_nontribal_any = bool(card_tags & _nontribal_plan_tags)
            if contributes_nontribal:
                bonus += min(1.4, 0.30 + unmet_nontribal * 0.06)
            elif unmet_nontribal > 0:
                bonus -= min(3.0, 0.45 + unmet_nontribal * 0.12)
            tribe_have = selected_tag_counts.get(_tribe_tag, 0)
            tribe_target = max(6, int(redundancy_targets.get(_tribe_tag, 6)))
            tribal_grace = max(4, min(8, tribe_target // 2))
            if not contributes_nontribal_any and tribe_have >= tribal_grace:
                over = tribe_have - tribal_grace + 1
                bonus -= min(4.2, 0.85 + over * 0.30)
        if active_plans & {"spells_velocity", "spell_cost_engine"}:
            spells_need = max(
                0,
                redundancy_targets.get("spells_enabler", 0) - selected_tag_counts.get("spells_enabler", 0),
            )
            spell_creature_cap = 14 if {"spells_velocity", "spell_cost_engine"} <= active_plans else 16
            if is_creature(card):
                supports_spell_shell = bool(card_tags & frozenset({"spells_payoff", "cost_reduction", "draw", "treasure_maker"}))
                creature_count = selected_type_counts.get("creature", 0)
                if creature_count >= spell_creature_cap:
                    over = creature_count - spell_creature_cap + 1
                    cap_pen = 0.9 + over * 0.30
                    if supports_spell_shell:
                        cap_pen *= 0.55
                    bonus -= min(5.0, cap_pen)
                if spells_need > 0 and not supports_spell_shell:
                    bonus -= min(3.4, 0.65 + spells_need * 0.16)
            if spells_need > 0 and not is_creature(card) and "spells_enabler" in card_tags:
                bonus += min(2.6, 0.45 + spells_need * 0.14)
        if "graveyard_hate" in card_tags:
            gy_shell = (
                selected_tag_counts.get("graveyard_payoff", 0)
                + selected_tag_counts.get("self_mill", 0)
                + selected_tag_counts.get("graveyard_enabler", 0)
            )
            if "graveyard_value" in active_plans:
                bonus -= 2.8
            elif gy_shell >= 6:
                bonus -= 1.6
        support_before, tension_before = interaction_support_tension_adjustment(
            selected_tag_counts, selected_role_counts
        )
        merged_tags = Counter(selected_tag_counts)
        for tag in card_tags:
            merged_tags[tag] += 1
        merged_roles = Counter(selected_role_counts)
        for role in set(card_roles):
            merged_roles[role] += 1
        support_after, tension_after = interaction_support_tension_adjustment(
            merged_tags, merged_roles
        )
        bonus += (support_after - support_before) * 0.9
        bonus -= (tension_after - tension_before) * 0.95
        if _strat_matchers:
            matched_groups = strategy_match_groups(card, _strat_matchers)
            if matched_groups:
                strategy_base = strat_bonus(card)
                strategy_blend = strategy_blend_multiplier(
                    matched_groups,
                    selected_strategy_counts,
                    len(selected_names),
                    nonland_slots,
                )
                bonus += strategy_base * (strategy_blend - 1.0)
            elif selected_names and len(selected_names) >= max(8, nonland_slots // 6):
                bonus -= 0.8 + min(1.2, len(selected_names) / max(nonland_slots, 1))
        # Engine flow critical gap: if the current plan has a tier below 50%
        # satisfied, heavily reward cards that fill it so the chain gets built.
        if _primary_plan and len(selected_names) >= 6:
            ef = validate_engine_flow(selected_tag_counts, _primary_plan, plan_profile)
            gap_tags = ef["critical_gap_tags"]
            if gap_tags and card_tags & gap_tags:
                # Weight by tier importance (win tier = 2.0, engine = 1.5 etc.)
                bonus += ef["gap_tier_weight"] * 1.2
        # Saturation penalty: once a core_tag is significantly above its redundancy
        # target and the card brings nothing else that's still needed, penalize
        # to yield slots to still-unmet engine pieces.
        for tag in core_tags:
            if tag not in card_tags:
                continue
            target = redundancy_targets.get(tag, 0)
            if target <= 0:
                continue
            have = selected_tag_counts.get(tag, 0)
            surplus = have - target
            if surplus > 2:
                other_unmet = {
                    t for t in core_tags
                    if t in redundancy_targets
                    and t != tag
                    and selected_tag_counts.get(t, 0) < redundancy_targets[t]
                }
                if not (card_tags & other_unmet):
                    bonus -= min(2.0, (surplus - 2) * 0.35)
        roles = set(classify_roles(card))
        current_avg_cmc = (
            (sum(get_cmc(db[n]) for n in selected_names) + get_cmc(card))
            / max(len(selected_names) + 1, 1)
        )
        hard_rules = ARCHETYPE_HARD_RULES.get(archetype, {})
        for role, need in dict(hard_rules.get("min_roles", {})).items():
            have = selected_role_counts.get(role, 0)
            if have < need and role in roles:
                bonus += (need - have) * (0.55 if role in {"threat", "tutor"} else 0.75)
        if archetype == "aggro" and "threat" in roles and get_cmc(card) <= 3:
            bonus += 0.85
        if archetype == "control" and is_creature(card) and get_cmc(card) <= 3 and "draw" not in roles:
            bonus -= 1.35
        if archetype == "combo" and get_cmc(card) >= 6 and "wincon" not in roles:
            bonus -= 1.20
        max_avg_cmc = hard_rules.get("max_avg_cmc")
        if isinstance(max_avg_cmc, (int, float)) and current_avg_cmc > float(max_avg_cmc) + 0.15:
            overflow = current_avg_cmc - float(max_avg_cmc)
            bonus -= overflow * 2.8
        return bonus

    # ── Phase -1: Infrastructure reservation ──────────────────────────────────
    # Lock in a minimum of foundational utility cards before strategy-driven
    # phases can fill all remaining slots with synergy or curve cards.
    # Each infrastructure role gets a slot budget; we pick the top-scored card
    # for each role until the budget is exhausted or slots run out.
    _infra_role_have: Counter = Counter()
    for _infra_role, _infra_n, _infra_cmc_max in INFRASTRUCTURE_SLOTS:
        for _sc, _card in global_scored:
            if _infra_role_have[_infra_role] >= _infra_n:
                break
            if len(selected_names) >= nonland_slots:
                break
            _cn = _card.get("name", "")
            if _cn in copy_counts or _cn == commander_name:
                continue
            if _infra_cmc_max is not None and get_cmc(_card) > _infra_cmc_max:
                continue
            _card_roles = classify_roles(_card)
            _card_tags = tag_index.get(_cn, frozenset())
            if _infra_role in _card_roles or _infra_role in _card_tags:
                _add_selected_card(_cn, 1)
                _infra_role_have[_infra_role] += 1

    # ── Phase 0: Mandatory density pre-fill ───────────────────────────────────
    # For each primary plan component, guarantee a floor of cards before the
    # curve-first Phase 1 can displace them with generic power picks.
    # We fill HALF the component need here; need_bonus in Phase 1 handles the rest.
    # Picks are drawn from global_scored (not CMC-bucketed) so the normal
    # score distribution naturally biases toward low-CMC cards.
    if _primary_plan and _primary_plan in PLAN_ENGINE_RULES:
        _engine_rule = PLAN_ENGINE_RULES[_primary_plan]
        for _label, _comp_tags, _comp_need in _engine_rule["components"]:
            # Patch tribal placeholder with actual tribe tag
            if _primary_plan == "tribal_synergy" and _label == "tribe_members" and primary_tribe:
                _comp_tags = frozenset({f"tribe_{primary_tribe}"})
                _comp_need = max(6, redundancy_targets.get(f"tribe_{primary_tribe}", _comp_need))
            if not _comp_tags:
                continue
            _have = sum(
                1 for n in selected_names
                if tag_index.get(n, frozenset()) & _comp_tags
            )
            _floor = max(0, (_comp_need + 1) // 2 - _have)  # fill up to half
            if _floor <= 0:
                continue

            def _passes_tribal_quality_gate(_card_obj: dict) -> bool:
                if not (_tribal_tension and _tribe_tag and _label == "tribe_members"):
                    return True
                _ctags = tag_index.get(_card_obj.get("name", ""), frozenset())
                if _tribe_tag not in _ctags:
                    return False
                if _ctags & _nontribal_plan_tags:
                    return True
                _roles = set(classify_roles(_card_obj))
                return bool(_roles & {"draw", "removal", "ramp", "counterspell", "tutor", "wincon"})

            _p0_candidates = sorted(
                (
                    (sc + _selection_need_bonus(c["name"]), c)
                    for sc, c in global_scored
                    if tag_index.get(c.get("name", ""), frozenset()) & _comp_tags
                    and c.get("name") not in copy_counts
                    and c.get("name") != commander_name
                    and _passes_tribal_quality_gate(c)
                ),
                key=lambda x: -x[0],
            )
            _filled = 0
            for _sc, _card in _p0_candidates:
                if _filled >= _floor or len(selected_names) >= nonland_slots:
                    break
                _n = _card.get("name", "")
                if _n in copy_counts:
                    continue
                _add_selected_card(_n, 1)
                _filled += 1

    # ── Phase 1: Fill per-CMC buckets ─────────────────────────────────────────
    # Process CMC values in order of priority for this archetype
    curve_targets = cfg["curve_targets"]
    # Sort CMC values by target count descending (fill most-needed buckets first)
    cmc_priority = sorted(curve_targets.keys(), key=lambda c: -curve_targets.get(c, 0))

    for cmc_int in cmc_priority:
        target = curve_targets.get(cmc_int, 0)
        if target <= 0:
            continue

        slots_remaining = target
        candidates = card_by_cmc.get(cmc_int, [])

        while slots_remaining > 0:
            # Always re-score with need_bonus before picking so plan-critical
            # cards (e.g. tribal members) win CMC slots over generic power cards.
            # Previously this was conditional on the first pick already having
            # need_bonus, which let strong off-plan cards lock in slots first.
            boosted_p1 = sorted(
                ((sc + _selection_need_bonus(c["name"]), c) for sc, c in candidates),
                key=lambda x: -x[0],
            )
            card = _weighted_pick(
                boosted_p1, set(copy_counts), diversity,
                deck_names=selected_names, db=db, tag_index=tag_index,
                deck_tag_counts=selected_tag_counts,
            )
            if card is None:
                break
            name = card["name"]
            current = copy_counts.get(name, 0)
            if current >= 1:
                continue

            want = desired_copies(card, 0.0)
            copies = min(want, slots_remaining, 1 - current)
            if copies <= 0:
                break

            _add_selected_card(name, copies)
            slots_remaining -= copies

    # ── Phase 2: Role fill for any still-underrepresented roles ───────────────
    role_counts: Counter = Counter()
    for name in selected_names:
        for role in classify_roles(db[name])[:1]:
            role_counts[role] += 1

    role_targets = {role: max(1, round(nonland_slots * ratio))
                    for role, ratio in cfg["role_ratios"].items()}

    max_cmc = cfg.get("max_cmc", 8)
    for role, tgt in role_targets.items():
        deficit = tgt - role_counts.get(role, 0)
        if deficit <= 0:
            continue
        role_candidates = [
            (sc, card) for sc, card in global_scored
            if get_cmc(card) <= max_cmc and role in classify_roles(card)
        ]
        while deficit > 0 and len(selected_names) < nonland_slots:
            boosted_role_candidates = sorted(
                ((sc + _selection_need_bonus(card["name"]), card) for sc, card in role_candidates),
                key=lambda x: -x[0],
            )
            card = _weighted_pick(
                boosted_role_candidates, set(copy_counts), diversity,
                deck_names=selected_names, db=db, tag_index=tag_index,
                deck_tag_counts=selected_tag_counts,
            )
            if card is None:
                break
            name = card["name"]
            current = copy_counts.get(name, 0)
            if current >= 1:
                continue
            roles = classify_roles(card)
            copies = min(1, deficit, nonland_slots - len(selected_names), 1 - current)
            if copies <= 0:
                break
            _add_selected_card(name, copies)
            for r in roles[:1]:
                role_counts[r] += copies
            deficit -= copies

    # ── Phase 3: Backfill remaining slots ─────────────────────────────────────
    max_cmc = cfg.get("max_cmc", 8)
    backfill_candidates = [
        (sc, card) for sc, card in global_scored
        if get_cmc(card) <= max_cmc
    ]
    while len(selected_names) < nonland_slots:
        boosted_backfill = sorted(
            ((sc + _selection_need_bonus(card["name"]), card) for sc, card in backfill_candidates),
            key=lambda x: -x[0],
        )
        card = _weighted_pick(
            boosted_backfill, set(copy_counts), diversity,
            deck_names=selected_names, db=db, tag_index=tag_index,
            deck_tag_counts=selected_tag_counts,
        )
        if card is None:
            break
        name = card["name"]
        current = copy_counts.get(name, 0)
        if current >= 1:
            continue
        can_add = min(1 - current, nonland_slots - len(selected_names))
        if can_add <= 0:
            break
        _add_selected_card(name, can_add)

    selected_names = selected_names[:nonland_slots]
    return [db[n] for n in selected_names]


# ─────────────────────────────────────────────────────────────────────────────
# EVOLUTIONARY REFINEMENT
# Mutation-based hill climbing: repeatedly swap the weakest card for a random
# candidate and keep the change if it improves overall fitness.
# ─────────────────────────────────────────────────────────────────────────────

def deck_fitness(
    cards: list[dict],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    archetype: str,
    strategy_words: list[str] | None = None,
    commander: dict | None = None,
    land_count: int | None = None,
    plan_profile: dict[str, object] | None = None,
) -> float:
    """Aggregate fitness function combining power, archetype fit, synergy, curve, and strategy."""
    cfg = ARCHETYPE_CONFIG[archetype]
    names = [c["name"] for c in cards]
    deck_colors = set()
    for c in cards:
        deck_colors |= set(c.get("color_identity") or [])
    if commander is not None:
        deck_colors |= set(commander.get("color_identity") or [])

    plan_profile = plan_profile or infer_commander_plan(commander)

    power_avg = sum(score_power(c) for c in cards) / max(len(cards), 1)
    arch_avg = sum(
        score_archetype_fit(c, archetype, classify_roles(c))
        for c in cards
    ) / max(len(cards), 1)

    synergy = deck_synergy_total(names, db, tag_index, plan_profile=plan_profile) / max(len(cards), 1)

    curve_ideal = cfg["curve_targets"]
    actual_curve = Counter(min(int(get_cmc(c)), 6) for c in cards)
    curve_dist = math.sqrt(sum(
        (actual_curve.get(cmc, 0) - tgt) ** 2
        for cmc, tgt in curve_ideal.items()
    ))
    curve_score = 1.0 / (1.0 + curve_dist / 10.0)

    effective_curve = Counter(min(int(round(estimate_effective_turn(c))), 6) for c in cards)
    effective_curve_dist = math.sqrt(sum(
        (effective_curve.get(cmc, 0) - tgt) ** 2
        for cmc, tgt in curve_ideal.items()
    ))
    effective_curve_score = 1.0 / (1.0 + effective_curve_dist / 10.0)

    # Strategy alignment: reward both raw coverage and concentration around a
    # coherent keyword cluster instead of treating all one-off matches equally.
    strat_score = 0.0
    strat_coherence_score = 0.0
    strat_intersection_score = 0.0
    off_strategy_rate = 1.0
    if strategy_words:
        matchers = build_strategy_matchers(strategy_words)
        strat_metrics = strategy_coherence_metrics(cards, matchers)
        strat_score = strat_metrics["match_rate"]
        strat_coherence_score = strat_metrics["coherence"]
        strat_intersection_score = strat_metrics["intersection_rate"]
        off_strategy_rate = strat_metrics["off_strategy_rate"]

    # Orphaned payoff penalty: payoff cards with no matching enablers in the deck
    # reduces fitness — the evolutionary phase will tend to replace them
    flat_tags: Counter = Counter()
    for c in cards:
        for tag in tag_index.get(c["name"], frozenset()):
            flat_tags[tag] += 1

    orphan_penalty = 0.0
    for payoff_tag, enabler_tag in PAYOFF_ENABLER_PAIRS:
        n_payoff = flat_tags.get(payoff_tag, 0)
        n_enabler = flat_tags.get(enabler_tag, 0)
        if n_payoff > 0 and n_enabler == 0:
            # Scale penalty: 0.4 per orphaned payoff card, min penalty of 1.0
            orphan_penalty += max(1.0, n_payoff * 0.4)

    # Change 1: named-card dependency penalty — cards that name absent cards
    _deck_name_set: frozenset[str] = frozenset(c.get("name", "") for c in cards)
    named_dep_penalty = 0.0
    for card in cards:
        missing = extract_named_dependencies(card) - _deck_name_set
        named_dep_penalty += min(3.0, len(missing) * 1.5)
    named_dep_penalty /= max(len(cards), 1)

    narrow_adjustment = _narrow_mechanic_adjustment(flat_tags)
    support_adjustment = _support_rule_adjustment(flat_tags)
    liability_cost = sum(liability_penalty(c) for c in cards) / max(len(cards), 1)

    priority_profile = derive_priority_profile(plan_profile)
    package_profile = choose_active_packages(plan_profile, cards, tag_index)
    structure_report = evaluate_archetype_structure(cards, tag_index, archetype)
    pair_support_bonus, pair_tension_penalty = interaction_support_tension_adjustment(
        flat_tags, structure_report["role_counts"]
    )
    archetype_coherence = archetype_coherence_score(cards, archetype)
    sim_land_count = land_count if land_count is not None else estimate_commander_land_count(cards, commander, archetype, plan_profile)
    sim = simulate_commander_goldfish(cards, commander, sim_land_count, tag_index, plan_profile=plan_profile)
    color_pressure = estimate_color_pressure(cards, deck_colors, sim_land_count)
    sim_score = (
        (1.0 - sim["dead_hand_rate"]) * 4.0 +
        min(1.0, sim["mean_mana_spent"] / 20.0) * 1.5 +
        max(0.0, 1.0 - (sim["mean_first_play_turn"] - 1.0) / 5.0) * 1.0 +
        sim["commander_on_curve_rate"] * 1.0 +
        sim["pair_assembly_rate"] * 1.0 +
        sim["engine_completion_rate"] * 1.75 +
        sim["finisher_seen_rate"] * 1.25
    )

    quadrant_totals = Counter()
    for card in cards:
        quadrant_totals.update(quadrant_profile(card))
    card_count = max(len(cards), 1)
    opening_score = quadrant_totals["opening"] / card_count
    parity_score = quadrant_totals["parity"] / card_count
    behind_score = quadrant_totals["behind"] / card_count
    ahead_score = quadrant_totals["ahead"] / card_count
    closing_score = quadrant_totals["closing"] / card_count
    quadrant_score = (
        min(1.0, opening_score / 0.65) * 1.0 +
        min(1.0, parity_score / 0.9) * 1.0 +
        min(1.0, behind_score / 0.55) * 0.8 +
        min(1.0, ahead_score / 0.65) * 0.7 +
        min(1.0, closing_score / 0.55) * 1.0
    )

    required_tags: dict[str, int] = dict(plan_profile.get("required_tags", {}))
    finisher_tags: frozenset[str] = frozenset(plan_profile.get("finisher_tags", frozenset({"wincon"})))
    core_tags: frozenset[str] = frozenset(priority_profile.get("core_tags", frozenset()))
    support_tags: frozenset[str] = frozenset(priority_profile.get("support_tags", frozenset()))
    redundancy_targets: dict[str, int] = dict(priority_profile.get("redundancy_targets", {}))
    active_plans: frozenset[str] = frozenset(plan_profile.get("plans", frozenset()))
    primary_tribe: str | None = plan_profile.get("primary_tribe")
    if primary_tribe and "tribal_synergy" in active_plans:
        _tribe_tag = f"tribe_{primary_tribe}"
        _base_target = int(redundancy_targets.get(_tribe_tag, 0))
        if _base_target > 0:
            _align = _tribal_alignment_ratio(primary_tribe, list(active_plans), cards, tag_index)
            redundancy_targets[_tribe_tag] = _scaled_tribal_target(_base_target, _align, active_plans)
    requirement_penalty = deck_requirement_penalty(
        cards,
        tag_index,
        classify_roles,
        get_subtypes,
        redundancy_targets=redundancy_targets,
        commander=commander,
        format_name="commander",
    )
    allowed_package_tags: frozenset[str] = frozenset(package_profile.get("allowed_tags", frozenset()))
    discouraged_package_tags: frozenset[str] = frozenset(package_profile.get("discouraged_tags", frozenset()))
    plan_penalty = 0.0
    for tag, count in required_tags.items():
        missing = max(0, count - flat_tags.get(tag, 0))
        if missing > 0:
            plan_penalty += missing * 0.45
    if not any(flat_tags.get(tag, 0) > 0 for tag in finisher_tags):
        plan_penalty += 2.0
    plan_summary = plan_component_summary(flat_tags, plan_profile, package_profile)
    for _label, have, need, ok in plan_summary["components"]:
        if not ok:
            plan_penalty += (need - have) * 0.4
    if plan_summary["components"] and plan_summary["closure_hits"] <= 0:
        plan_penalty += 1.5
    redundancy_bonus = 0.0
    redundancy_penalty = 0.0
    for tag, target in redundancy_targets.items():
        have = flat_tags.get(tag, 0)
        if have >= target:
            redundancy_bonus += 0.22 if tag in core_tags else 0.12
        else:
            missing = target - have
            redundancy_penalty += missing * (0.35 if tag in core_tags else 0.18)
    core_hits = sum(1 for c in cards if tag_index.get(c["name"], frozenset()) & core_tags)
    support_hits = sum(1 for c in cards if tag_index.get(c["name"], frozenset()) & support_tags)
    offplan_hits = sum(1 for c in cards if not (tag_index.get(c["name"], frozenset()) & (core_tags | support_tags | finisher_tags)))
    if core_tags and core_hits < max(6, len(cards) // 6):
        plan_penalty += (max(6, len(cards) // 6) - core_hits) * 0.18
    if support_tags and support_hits < max(4, len(cards) // 8):
        plan_penalty += (max(4, len(cards) // 8) - support_hits) * 0.10
    offplan_allowance = max(6, len(cards) // 5)
    if offplan_hits > offplan_allowance:
        plan_penalty += (offplan_hits - offplan_allowance) * 0.22
    plan_penalty += max(0.0, 0.72 - archetype_coherence) * 6.0
    if strategy_words:
        plan_penalty += max(0.0, off_strategy_rate - 0.28) * 7.5
        plan_penalty += max(0.0, 0.45 - strat_coherence_score) * 3.5
    if allowed_package_tags:
        package_hits = sum(1 for c in cards if tag_index.get(c["name"], frozenset()) & allowed_package_tags)
        if package_hits < max(14, len(cards) // 3):
            plan_penalty += (max(14, len(cards) // 3) - package_hits) * 0.10
    if discouraged_package_tags:
        tertiary_hits = sum(
            1 for c in cards
            if (tag_index.get(c["name"], frozenset()) & discouraged_package_tags)
            and not (tag_index.get(c["name"], frozenset()) & allowed_package_tags)
        )
        tertiary_allowance = max(5, len(cards) // 10)
        if tertiary_hits > tertiary_allowance:
            plan_penalty += (tertiary_hits - tertiary_allowance) * 0.16
    plan_penalty += max(0.0, 1.0 - color_pressure["color_score"]) * 2.0
    if color_pressure["shortage"] > 0:
        plan_penalty += min(2.5, color_pressure["shortage"] * 0.18)
    plan_penalty += structure_report["penalty"]
    if structure_report["hard_fail"]:
        plan_penalty += 10.0
    if active_plans & {"spells_velocity", "spell_cost_engine"}:
        creature_count = sum(1 for c in cards if is_creature(c))
        spell_creature_cap = 14 if {"spells_velocity", "spell_cost_engine"} <= active_plans else 16
        if creature_count > spell_creature_cap:
            plan_penalty += (creature_count - spell_creature_cap) * 0.95
        spells_enabler_need = max(
            required_tags.get("spells_enabler", 0),
            redundancy_targets.get("spells_enabler", 0),
        )
        if spells_enabler_need > 0 and flat_tags.get("spells_enabler", 0) < spells_enabler_need:
            plan_penalty += (spells_enabler_need - flat_tags.get("spells_enabler", 0)) * 0.42
    if "graveyard_value" in active_plans:
        gy_hate = flat_tags.get("graveyard_hate", 0)
        if gy_hate > 0:
            plan_penalty += gy_hate * 1.4
    slot_baseline = _slot_mix_from_cards(cards)
    tag_slot_affinity = _build_tag_slot_affinity(cards, tag_index, slot_baseline)
    desired_slot_mix, _unmet_tags, unresolved_ratio = _slot_pressure_from_deficits(
        flat_tags,
        required_tags,
        redundancy_targets,
        core_tags,
        tag_slot_affinity,
        slot_baseline,
    )
    actual_slot_mix = slot_baseline
    slot_mismatch = 0.5 * sum(
        abs(actual_slot_mix.get(slot, 0.0) - desired_slot_mix.get(slot, 0.0))
        for slot in _SLOT_TYPES
    )
    if unresolved_ratio > 0:
        plan_penalty += slot_mismatch * (1.0 + unresolved_ratio * 2.4)

    # Engine flow score: reward decks whose fuel→engine→payload→win chain is complete.
    # A deck missing a critical tier (< 50% satisfied) loses up to 3.5 pts.
    primary_plan_name = package_profile.get("primary_plan") or ""
    ef = validate_engine_flow(flat_tags, primary_plan_name, plan_profile)
    engine_flow_score = ef["overall_score"] * 3.5  # max 3.5 bonus for complete chain

    # Win condition availability: reward having at least one clear win path.
    wc_results = detect_win_conditions(names, flat_tags)
    wc_available = sum(1 for w in wc_results if w["available"])
    win_con_score = min(1.0, wc_available / 1.0) * 2.5  # up to 2.5 bonus for having win paths

    if strategy_words:
        return (
            power_avg        * 0.22 +
            arch_avg * 10    * 0.20 +
            synergy          * 0.14 +
            curve_score * 10 * 0.11 +
            effective_curve_score * 10 * 0.09 +
            strat_score * 10 * 0.14 +
            strat_coherence_score * 2.4 +
            strat_intersection_score * 1.2 +
            sim_score        * 0.14 +
            quadrant_score   * 0.09
            + narrow_adjustment
            + support_adjustment
            + redundancy_bonus
            + pair_support_bonus
            + archetype_coherence * 1.8
            + engine_flow_score
            + win_con_score
            - orphan_penalty
            - named_dep_penalty
            - liability_cost
            - requirement_penalty
            - redundancy_penalty
            - pair_tension_penalty
            - plan_penalty
        )
    return (
        power_avg       * 0.25 +
        arch_avg * 10   * 0.25 +
        synergy         * 0.18 +
        curve_score * 10 * 0.17 +
        effective_curve_score * 10 * 0.10 +
        sim_score       * 0.13 +
        quadrant_score  * 0.10
        + narrow_adjustment
        + support_adjustment
        + redundancy_bonus
        + pair_support_bonus
        + archetype_coherence * 1.8
        + engine_flow_score
        + win_con_score
        - orphan_penalty
        - named_dep_penalty
        - liability_cost
        - requirement_penalty
        - redundancy_penalty
        - pair_tension_penalty
        - plan_penalty
    )


def evolutionary_refine(
    nonlands: list[dict],
    candidate_pool: list[dict],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    archetype: str,
    generations: int = 200,
    max_cmc: float = 99,
    strategy_words: list[str] | None = None,
    diversity: float = 1.0,
    commander: dict | None = None,
    land_count: int | None = None,
    plan_profile: dict[str, object] | None = None,
    strict_tribal: bool = False,
) -> list[dict]:
    """Mutation-based evolutionary refinement with limited exploratory moves."""
    current = list(nonlands)
    plan_profile = plan_profile or infer_commander_plan(commander)
    priority_profile = derive_priority_profile(plan_profile)
    required_tags: dict[str, int] = dict(plan_profile.get("required_tags", {}))
    redundancy_targets: dict[str, int] = dict(priority_profile.get("redundancy_targets", {}))
    core_tags: frozenset[str] = frozenset(priority_profile.get("core_tags", frozenset()))
    current_fitness = deck_fitness(
        current, db, tag_index, archetype, strategy_words,
        commander=commander, land_count=land_count, plan_profile=plan_profile,
    )
    best = list(current)
    best_fitness = current_fitness
    current_names = {c["name"] for c in current}

    # Respect max CMC constraint during mutation; never allow the commander back in
    _evo_commander_name = commander.get("name") if commander else None
    _evo_primary_tribe: str | None = (plan_profile or {}).get("primary_tribe")
    eligible_pool = [
        c for c in candidate_pool
        if get_cmc(c) <= max_cmc and c.get("name") != _evo_commander_name
    ]

    # Strict tribal: purge non-tribe creatures from the replacement pool so
    # evolution can only swap in tribe members (non-creatures are kept).
    if strict_tribal and _evo_primary_tribe:
        _evo_tribe_tag = f"tribe_{_evo_primary_tribe}"
        eligible_pool = [
            c for c in eligible_pool
            if "Creature" not in (c.get("type_line") or "")
            or _evo_tribe_tag in tag_index.get(c.get("name", ""), frozenset())
        ]

    _evo_slot_baseline = _slot_mix_from_cards(eligible_pool)
    _evo_tag_slot_affinity = _build_tag_slot_affinity(eligible_pool, tag_index, _evo_slot_baseline)

    candidates = [c for c in eligible_pool if c["name"] not in current_names]

    # Per-card score for picking weakest: power + archetype + strategy
    _evo_matchers = build_strategy_matchers(strategy_words) if strategy_words else []

    def card_score(c: dict, deck_state: dict[str, object] | None = None) -> float:
        base = score_power(c) + score_archetype_fit(c, archetype, classify_roles(c)) * 10
        if _evo_matchers and card_matches_strategy(c, _evo_matchers):
            base += 6.0
        # Mirror the composite-level structural penalties so evolution
        # correctly identifies conditionally-broken cards as weak
        c_oracle = (c.get("oracle_text") or "").lower()
        if re.search(r"activate only if .{0,80}(power|toughness) is [3-9]\d* or greater", c_oracle):
            base -= 4.0
        if re.search(r"can't (attack|block) (or block |or attack )?unless (you.ve |you have )", c_oracle):
            base -= 2.5
        base += _narrow_mechanic_adjustment(
            Counter(tag for tag in tag_index.get(c["name"], frozenset())),
            tag_index.get(c["name"], frozenset()),
        )
        base += _support_rule_adjustment(
            Counter(tag for tag in tag_index.get(c["name"], frozenset())),
            tag_index.get(c["name"], frozenset()),
        )
        base -= liability_penalty(c)
        base -= commander_role_penalty(c)
        if deck_state is not None:
            req_penalty, _unmet = evaluate_card_requirements(
                c, deck_state, format_name="commander"
            )
            base -= req_penalty
        # (Non-tribe creatures are excluded from eligible_pool when strict_tribal
        # is active, so no per-card penalty is needed here.)
        return base

    def dynamic_theme_bonus(
        c: dict,
        deck_state: dict[str, object],
        strategy_counts: Counter,
    ) -> float:
        bonus = 0.0
        card_tags = tag_index.get(c.get("name", ""), frozenset())
        roles = classify_roles(c)
        arch_fit = score_archetype_fit(c, archetype, roles)
        arch_blend = archetype_blend_multiplier(
            roles,
            archetype,
            deck_state["role_counts"],
            len(current),
            len(current),
        )
        bonus += arch_fit * 3.0 * (arch_blend - 1.0)
        pressure_mix, unmet_tags, unresolved_ratio = _slot_pressure_from_deficits(
            deck_state["tag_counts"],
            required_tags,
            redundancy_targets,
            core_tags,
            _evo_tag_slot_affinity,
            _evo_slot_baseline,
        )
        bonus += _slot_pressure_adjustment(
            c,
            bool(card_tags & unmet_tags),
            pressure_mix,
            unresolved_ratio,
        )
        if _evo_matchers:
            matched_groups = strategy_match_groups(c, _evo_matchers)
            if matched_groups:
                strategy_base = 6.0
                strategy_blend = strategy_blend_multiplier(
                    matched_groups,
                    strategy_counts,
                    len(current),
                    len(current),
                )
                bonus += strategy_base * (strategy_blend - 1.0)
            else:
                bonus -= 1.0
        return bonus

    base_candidate_scores: dict[str, float] = {
        c["name"]: card_score(c) for c in eligible_pool
    }

    for _ in range(generations):
        if not candidates:
            break

        # Score each card in the current deck; pick a weak one to replace
        current_state = build_deck_state(
            current, tag_index, classify_roles, get_subtypes, commander=commander
        )
        current_strategy_counts: Counter = Counter()
        if _evo_matchers:
            for card in current:
                for group in strategy_match_groups(card, _evo_matchers):
                    current_strategy_counts[group] += 1
        card_scores = [
            (i, card_score(c, current_state))
            for i, c in enumerate(current)
        ]
        card_scores.sort(key=lambda x: x[1])  # worst first

        # Higher diversity = consider replacing cards further up the rankings,
        # exploring more of the search space at the cost of some consistency.
        # diversity 0 → worst 1/6;  1.0 → worst 1/3;  3.0 → worst 2/3
        replace_fraction = min(0.67, max(0.10, diversity / 4.5))
        pool_size = max(1, int(len(card_scores) * replace_fraction))
        worst_idx = card_scores[random.randint(0, pool_size - 1)][0]
        candidate_count = len(candidates)
        shortlist_size = min(
            candidate_count,
            max(64, min(512, 64 + int(diversity * 96)))
        )
        if shortlist_size < candidate_count:
            sampled = random.sample(candidates, shortlist_size)
        else:
            sampled = list(candidates)
        structure_report = evaluate_archetype_structure(current, tag_index, archetype)
        removed_card = current[worst_idx]
        removed_roles = set(classify_roles(removed_card))
        needed_roles = set(structure_report["needed_roles"])
        if needed_roles:
            needed_sampled = [
                c for c in sampled
                if set(classify_roles(c)) & needed_roles
            ]
            if needed_sampled:
                sampled = needed_sampled
        elif removed_roles:
            role_preserving = [
                c for c in sampled
                if set(classify_roles(c)) & removed_roles
            ]
            if role_preserving:
                sampled = role_preserving
        if archetype == "control" and structure_report["role_counts"].get("threat", 0) > 0:
            noncreature_sampled = [c for c in sampled if not is_creature(c)]
            if noncreature_sampled and is_creature(removed_card):
                sampled = noncreature_sampled
        candidate_scores = sorted(
            (
                (
                    base_candidate_scores[c["name"]] + dynamic_theme_bonus(c, current_state, current_strategy_counts),
                    c,
                )
                for c in sampled
            ),
            key=lambda x: -x[0],
        )
        replacement = _weighted_pick(candidate_scores, set(), diversity)
        if replacement is None:
            break

        new_deck = list(current)
        new_deck[worst_idx] = replacement
        new_fitness = deck_fitness(
            new_deck, db, tag_index, archetype, strategy_words,
            commander=commander, land_count=land_count, plan_profile=plan_profile,
        )

        accept = new_fitness > current_fitness
        if not accept and diversity > 0:
            # Small simulated-annealing style escape hatch to avoid identical
            # local optima across runs with the same broad parameters.
            tolerance = 0.15 + diversity * 0.25
            if new_fitness >= current_fitness - tolerance and random.random() < 0.04 * diversity:
                accept = True

        if accept:
            current = new_deck
            current_fitness = new_fitness
            if current_fitness > best_fitness:
                best = list(current)
                best_fitness = current_fitness
            current_names = {c["name"] for c in current}
            candidates = [c for c in eligible_pool if c["name"] not in current_names]

    return best


def deck_shape_signature(cards: list[dict], tag_index: dict[str, frozenset[str]]) -> tuple:
    """Bucket a deck into a coarse shape for quality-diversity selection."""
    creature_count = sum(1 for c in cards if is_creature(c))
    avg_cmc = sum(get_cmc(c) for c in cards) / max(len(cards), 1)
    flat_tags = _tag_counter_from_cards(cards, tag_index)
    graveyard = flat_tags.get("graveyard_payoff", 0) + flat_tags.get("graveyard_enabler", 0)
    tokens = flat_tags.get("token_maker", 0)
    spells = flat_tags.get("spells_enabler", 0)
    interaction = sum(1 for c in cards if any(r in classify_roles(c) for r in ("removal", "counterspell", "disruption")))

    return (
        min(4, creature_count // 12),
        min(4, int(avg_cmc)),
        min(4, graveyard // 4),
        min(4, tokens // 3),
        min(4, spells // 4),
        min(4, interaction // 4),
    )


def compute_synergy_rating(
    nonlands: list[dict],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    plan_profile: dict[str, object] | None = None,
) -> tuple[int, float]:
    """
    Return (display_score_0_100, raw_per_card_synergy).
    Uses deck-level synergy total and adds a small tribal focus bonus only when
    tribal_synergy is an active inferred plan.
    """
    names = [c.get("name", "") for c in nonlands if c.get("name")]
    if not names:
        return 0, 0.0
    synergy_total = deck_synergy_total(names, db, tag_index, plan_profile=plan_profile)
    per_card = synergy_total / max(len(nonlands), 1)
    plans = frozenset((plan_profile or {}).get("plans", frozenset()))
    tribal_bonus = 0.0
    if "tribal_synergy" in plans:
        tribe_counter: Counter = Counter()
        for card in nonlands:
            for sub in get_subtypes(card):
                tribe_counter[sub] += 1
        top_tribe = tribe_counter.most_common(1)[0][1] if tribe_counter else 0
        if top_tribe >= 8:
            tribal_bonus = min(20.0, (top_tribe - 8) * 1.5)
    display = int(max(0, min(100, round(per_card * 60.0 + tribal_bonus))))
    return display, per_card


def generate_commander_candidates(
    all_nonlands: list[dict],
    db: dict,
    tag_index: dict[str, frozenset[str]],
    archetype: str,
    colors: set[str],
    strategy_hint: str,
    max_rarity: str,
    commander: dict,
    diversity: float,
    generations: int,
    no_evolve: bool,
    plan_profile: dict[str, object],
    num_candidates: int = 6,
    strict_tribal: bool = False,
    ignore_tribal: bool = False,
) -> tuple[list[dict], int]:
    """
    Generate multiple candidate decks and keep the best deck per shape bucket.
    Returns the strongest surviving deck and its chosen land count.
    """
    archive: dict[tuple, tuple[float, list[dict], int]] = {}
    max_cmc = ARCHETYPE_CONFIG[archetype].get("max_cmc", 99)
    strat_words = list({
        *extract_strategy_terms(strategy_hint),
        *extract_strategy_terms(commander_auto_strategy(commander, ignore_tribal=ignore_tribal)),
    } - {""})

    for idx in range(max(1, num_candidates)):
        print(f"  Candidate {idx + 1}/{max(1, num_candidates)}...", file=sys.stderr)
        seed_nonlands = select_nonlands(
            all_nonlands, db, tag_index, archetype, colors,
            strategy_hint, COMMANDER_MAIN_SIZE - ARCHETYPE_CONFIG[archetype]["land_count"], max_rarity,
            diversity=diversity,
            commander=commander,
            plan_profile=plan_profile,
            strict_tribal=strict_tribal,
            ignore_tribal=ignore_tribal,
        )
        land_count = estimate_commander_land_count(seed_nonlands, commander, archetype, plan_profile)
        nonland_slots = COMMANDER_MAIN_SIZE - land_count
        candidate = select_nonlands(
            all_nonlands, db, tag_index, archetype, colors,
            strategy_hint, nonland_slots, max_rarity,
            diversity=diversity,
            commander=commander,
            plan_profile=plan_profile,
            strict_tribal=strict_tribal,
            ignore_tribal=ignore_tribal,
        )
        if not no_evolve:
            candidate = evolutionary_refine(
                candidate, all_nonlands, db, tag_index, archetype, generations,
                max_cmc=max_cmc,
                strategy_words=strat_words,
                diversity=diversity,
                commander=commander,
                land_count=land_count,
                plan_profile=plan_profile,
                strict_tribal=strict_tribal,
            )

        fitness = deck_fitness(
            candidate, db, tag_index, archetype, strat_words,
            commander=commander, land_count=land_count, plan_profile=plan_profile,
        )
        shape = deck_shape_signature(candidate, tag_index)
        prev = archive.get(shape)
        if prev is None or fitness > prev[0]:
            archive[shape] = (fitness, candidate, land_count)

    best_fitness, best_cards, best_land_count = max(archive.values(), key=lambda x: x[0])
    return best_cards, best_land_count


# ─────────────────────────────────────────────────────────────────────────────
# MANA BASE CONSTRUCTION
# Implements Frank Karsten's pip-analysis method.
# ─────────────────────────────────────────────────────────────────────────────

_MANA_RESTRICTION_RE = re.compile(
    r"spend this mana only|activate only if|only to cast|only to activate"
    r"|deals \d+ damage to you",
    re.IGNORECASE,
)
_COLOR_SYM: dict[str, str] = {"W": "w", "U": "u", "B": "b", "R": "r", "G": "g"}

# Land subtypes → colors they produce (for fetch land inference)
_LAND_TYPE_COLORS: dict[str, str] = {
    "plains": "W", "island": "U", "swamp": "B", "mountain": "R", "forest": "G",
}
_FETCH_CLAUSE_RE = re.compile(
    r"search your library for [^.]+",
    re.IGNORECASE,
)

def land_produces(land: dict) -> set[str]:
    """
    Colors a land can produce for general (unrestricted) use.
    Parses oracle text line-by-line, skipping lines that restrict how the mana
    may be spent (e.g. 'spend this mana only to cast a Dragon spell').
    Does NOT fall back to Scryfall's produced_mana field, which lists every color
    a card can ever produce regardless of restrictions.
    """
    oracle = (land.get("oracle_text") or "")
    if not oracle:
        return set()

    # Strip quoted text (granted abilities — the land doesn't produce that mana itself)
    oracle_stripped = re.sub(r'"[^"]*"', "", oracle)

    produced: set[str] = set()
    for line in oracle_stripped.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        low = stripped.lower()

        # Skip lines that restrict mana spending / conditional activation
        if _MANA_RESTRICTION_RE.search(low):
            continue

        # Detect explicit colored symbols: {W}, {U}, {B}, {R}, {G}
        for color in _COLOR_SYM:
            if f"{{{color}}}" in stripped:
                produced.add(color)

        # "add one mana of any color" without restrictions on the same line
        if "any color" in low:
            produced.update("WUBRG")

    # Fetch lands: "search your library for a Swamp or Mountain card"
    if not produced:
        oracle_low = oracle_stripped.lower()
        if "search your library for" in oracle_low and ("sacrifice" in oracle_low or "pay" in oracle_low):
            m = _FETCH_CLAUSE_RE.search(oracle_stripped)
            if m:
                clause = m.group(0).lower()
                for land_type, color in _LAND_TYPE_COLORS.items():
                    if land_type in clause:
                        produced.add(color)

    return produced


_RELIABLE_UNLESS_RE = re.compile(
    r"unless you control (?:two or fewer|a (?:plains|island|swamp|mountain|forest)|two or more basic)",
    re.IGNORECASE,
)

def is_reliable_untapped(land: dict) -> bool:
    """
    True if the land enters untapped reliably (enough for competitive play).
    Reliable conditions:
      - No "enters tapped" at all (pain lands, simple tapped check)
      - "pay 2 life" (shock lands)
      - "unless you control two or fewer other lands" (fast lands)
      - "unless you control a [basic type]" (check lands)
      - "unless you control two or more basic lands" (battle lands)
    Unreliable conditions:
      - "unless a player has N or less life" (player life-based)
      - "unless you control a legendary" or unusual game-state conditions
    """
    oracle = (land.get("oracle_text") or "").lower()
    if "enters tapped" not in oracle:
        return True
    if "pay 2 life" in oracle:
        return True
    if _RELIABLE_UNLESS_RE.search(oracle):
        return True
    return False


def build_mana_base(
    nonlands: list[dict],
    land_pool: list[dict],
    colors: set[str],
    land_count: int,
    plan_tags: frozenset[str] | None = None,
) -> list[dict]:
    """
    Select lands to form a Karsten-sound mana base.
    Returns a list of land card dicts (with repetition for multiple copies).
    plan_tags: frozenset of plan-relevant tags used to boost contextually useful lands.
    """
    if not colors:
        return []

    # ── Step 1: Analyze pip demands ──────────────────────────────────────────
    # For each color, track the most demanding (most pips, earliest turn) cost
    pip_demand: dict[str, dict] = {
        c: {"pips": 0, "turn": 7} for c in colors
    }
    for card in nonlands:
        mc = card.get("mana_cost") or ""
        cmc = get_cmc(card)
        turn = max(1, min(int(cmc), 4))
        pips = count_pips(mc)
        for color in colors:
            p = pips.get(color, 0)
            if p == 0:
                continue
            if (p > pip_demand[color]["pips"] or
                    (p == pip_demand[color]["pips"] and turn < pip_demand[color]["turn"])):
                pip_demand[color] = {"pips": p, "turn": turn}

    # ── Step 2: Required sources per color (Karsten table) ───────────────────
    required: dict[str, int] = {}
    for color in colors:
        demand = pip_demand[color]
        p_clamped = min(demand["pips"], 3) if demand["pips"] > 0 else 1
        t_clamped = max(1, min(demand["turn"], 4))
        base_sources = KARSTEN_SOURCES.get(p_clamped, {}).get(t_clamped, 12)
        # Scale for deck's actual land count (table assumes 24 lands)
        required[color] = round(base_sources * (land_count / 24))

    # Normalize to land count
    total_req = sum(required.values()) or 1
    allocation = {
        c: max(4, round(required[c] / total_req * land_count))
        for c in colors
    }
    # Correct rounding drift
    diff = land_count - sum(allocation.values())
    if diff:
        primary = max(allocation, key=allocation.get)
        allocation[primary] += diff

    # ── Step 3: Select lands greedily ────────────────────────────────────────
    # Sort land pool.  Priority:
    #   1. Reliable untapped before tapped (unreliable)
    #   2. More of our needed colors first (2-color dual > single basic)
    #   3. Fewer extra colors (Blood Crypt exact B/R > 5-color Mana Confluence)
    # This ensures specialized duals (shock, fast, check) beat broad 5-color sources.
    # Change 7: plan-aware land priority
    _plan_tags = plan_tags or frozenset()
    # Utility oracle patterns rewarded by specific plan tags
    _LAND_UTILITY_PATTERNS: list[tuple[frozenset[str], re.Pattern]] = [
        (frozenset({"draw", "draw_count_payoff"}), re.compile(r"\bdraw a card\b", re.I)),
        (frozenset({"graveyard_payoff", "graveyard_enabler", "self_mill"}),
         re.compile(r"\bmill\b|\bgraveyard\b", re.I)),
        (frozenset({"artifact_payoff", "artifact"}),
         re.compile(r"\bartifact\b", re.I)),
        (frozenset({"token_maker", "token_payoff"}),
         re.compile(r"\bcreate.{0,20}token\b", re.I)),
        (frozenset({"lifegain", "life_as_resource"}),
         re.compile(r"\bgain \d+ life\b|\bgain life\b", re.I)),
    ]

    def _land_utility_bonus(land: dict) -> float:
        """Return a small positive bonus if the land has oracle utility matching the plan."""
        if not _plan_tags:
            return 0.0
        oracle = (land.get("oracle_text") or "").lower()
        bonus = 0.0
        for tag_set, pattern in _LAND_UTILITY_PATTERNS:
            if tag_set & _plan_tags and pattern.search(oracle):
                bonus += 0.5
        return bonus

    # Cap: no more than 1/5 of the land slots may be tapped-only generic utility
    _generic_utility_cap = max(3, land_count // 5)
    _generic_utility_count = 0

    def land_priority(land: dict) -> tuple:
        prod = land_produces(land)
        in_colors = prod & colors           # colors we actually want
        extra = prod - colors               # colors we don't need
        reliable = is_reliable_untapped(land)
        utility = _land_utility_bonus(land)
        # Tiebreak alphabetically for determinism across runs
        # Lower tuple = higher priority (sort ascending)
        return (not reliable, -len(in_colors), len(extra), -utility, land.get("name", ""))

    sorted_lands = sorted(land_pool, key=land_priority)

    remaining = dict(allocation)
    selected: list[dict] = []

    for land in sorted_lands:
        if sum(remaining.values()) <= 0:
            break

        prod = land_produces(land) & colors
        if not prod:
            continue

        is_basic = "Basic" in (land.get("type_line") or "")
        # Brawl singleton: basics can stack, every non-basic is limited to 1
        max_copies = 20 if is_basic else 1

        # Change 7: cap tapped-only non-basic utility lands
        _is_tapped_nonbasic = (not is_basic) and (not is_reliable_untapped(land))
        if _is_tapped_nonbasic and _generic_utility_count >= _generic_utility_cap:
            continue

        copies_added = 0
        for _ in range(max_copies):
            # Stop if all needs satisfied or we've run out of slots
            if sum(remaining.values()) <= 0 or len(selected) >= land_count:
                break
            # Check if any of its colors are still needed
            if not any(remaining.get(c, 0) > 0 for c in prod):
                break
            selected.append(land)
            for c in prod:
                if remaining.get(c, 0) > 0:
                    remaining[c] -= 1
            copies_added += 1
        if _is_tapped_nonbasic and copies_added > 0:
            _generic_utility_count += copies_added

    # ── Step 4: Backfill with basics if still short ──────────────────────────
    # Identify one basic land per color
    basic_by_color: dict[str, dict] = {}
    for land in land_pool:
        if "Basic" not in (land.get("type_line") or ""):
            continue
        prod = land_produces(land) & colors
        for c in prod:
            if c not in basic_by_color:
                basic_by_color[c] = land

    while len(selected) < land_count:
        # Add basics for the most under-served color
        needed_colors = {c: allocation[c] for c in colors}
        served = Counter(
            c for land in selected
            for c in (land_produces(land) & colors)
        )
        deficit = {c: needed_colors[c] - served.get(c, 0) for c in colors}
        most_needed = max(deficit, key=deficit.get, default=None)
        if most_needed and most_needed in basic_by_color:
            selected.append(basic_by_color[most_needed])
            served[most_needed] += 1
        elif basic_by_color:
            selected.append(next(iter(basic_by_color.values())))
        else:
            break

    return selected[:land_count]


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT
# ─────────────────────────────────────────────────────────────────────────────

def _dfc_display_name(name: str) -> str:
    """Return the front-face name for double-faced cards."""
    return name.split(" // ")[0] if " // " in name else name


def format_commander(commander: dict, nonlands: list[dict], lands: list[dict]) -> str:
    """Format a Commander deck list (plain name format)."""
    lines = ["Commander"]
    lines.append(f"1 {_dfc_display_name(commander['name'])}")
    lines.append("")
    lines.append("Deck")
    for card in sorted(nonlands, key=lambda c: (get_cmc(c), c["name"])):
        lines.append(f"1 {_dfc_display_name(card['name'])}")
    lines.append("")
    lines.append("// Lands")
    land_counts = Counter(c["name"] for c in lands)
    for name, count in sorted(land_counts.items()):
        lines.append(f"{count} {_dfc_display_name(name)}")

    return "\n".join(lines)


def format_commander_arena(commander: dict, nonlands: list[dict], lands: list[dict]) -> str:
    """Format a Commander deck list with set code and collector number."""
    def _line(card: dict, count: int = 1) -> str:
        display  = _dfc_display_name(card.get("name", ""))
        set_code = (card.get("set") or "").upper()
        cn       = str(card.get("collector_number") or "").strip()
        if set_code and cn:
            return f"{count} {display} ({set_code}) {cn}"
        return f"{count} {display}"

    land_counts  = Counter(c["name"] for c in lands)
    land_map     = {c["name"]: c for c in lands}

    lines = ["Commander"]
    lines.append(_line(commander))
    lines.append("")
    lines.append("Deck")
    for card in sorted(nonlands, key=lambda c: (get_cmc(c), c["name"])):
        lines.append(_line(card))
    lines.append("")
    lines.append("// Lands")
    for name, count in sorted(land_counts.items()):
        lines.append(_line(land_map[name], count))

    return "\n".join(lines)


# Aliases for compatibility with GUI code that calls brawl-style names
def format_brawl(commander: dict, nonlands: list[dict], lands: list[dict]) -> str:
    return format_commander(commander, nonlands, lands)

def format_brawl_arena(commander: dict, nonlands: list[dict], lands: list[dict]) -> str:
    return format_commander_arena(commander, nonlands, lands)


def print_analysis(nonlands: list[dict], lands: list[dict], archetype: str,
                   db: dict, tag_index: dict[str, frozenset[str]],
                   plan_profile: dict[str, object] | None = None) -> None:
    """Print a human-readable deck analysis to stderr."""
    all_cards = nonlands + lands
    w = 60

    print(f"\n{'─'*w}", file=sys.stderr)
    print(f"  DECK ANALYSIS — {archetype.upper()} ({len(all_cards)} cards)", file=sys.stderr)
    print(f"{'─'*w}", file=sys.stderr)

    # Mana curve
    curve = Counter(min(int(get_cmc(c)), 7) for c in nonlands)
    print("\nMana Curve (nonlands):", file=sys.stderr)
    for cmc in sorted(curve):
        label = f"{cmc}+" if cmc == 7 else str(cmc)
        bar = "█" * curve[cmc]
        print(f"  CMC {label}: {bar:20s} ({curve[cmc]})", file=sys.stderr)
    avg_cmc = sum(get_cmc(c) for c in nonlands) / max(len(nonlands), 1)
    print(f"  Avg CMC: {avg_cmc:.2f}", file=sys.stderr)

    # Role breakdown (count ALL roles a card fills, not just the primary)
    role_counts: Counter = Counter()
    for card in nonlands:
        for role in set(classify_roles(card)):
            role_counts[role] += 1
    print("\nRole Breakdown (cards filling each role):", file=sys.stderr)
    for role, count in role_counts.most_common():
        print(f"  {role.capitalize():<16s}: {count}", file=sys.stderr)

    # Color pips
    pip_totals: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
    for card in nonlands:
        mc = card.get("mana_cost") or ""
        for color, val in count_pips(mc).items():
            pip_totals[color] += val
    active = {c: v for c, v in pip_totals.items() if v > 0}
    if active:
        total_pips = sum(active.values()) or 1
        print("\nPip Distribution:", file=sys.stderr)
        for color, count in sorted(active.items(), key=lambda x: -x[1]):
            pct = count / total_pips * 100
            print(f"  {color}: {count} pips ({pct:.0f}%)", file=sys.stderr)

    # Active synergies
    flat_tags: Counter = Counter()
    for name in {c["name"] for c in nonlands}:
        for tag in tag_index.get(name, frozenset()):
            flat_tags[tag] += 1
    active_syn = [(t, c) for t, c in flat_tags.items() if is_reportable_synergy(t, c, flat_tags)]
    if active_syn:
        print("\nActive Synergies:", file=sys.stderr)
        for tag, count in sorted(active_syn, key=lambda x: -x[1]):
            label = tag.replace("_", " ").title()
            print(f"  {label:<28s}: {count}", file=sys.stderr)

    support_gaps = []
    for name, rule in SUPPORT_VALIDATION_RULES.items():
        payoff = sum(flat_tags.get(tag, 0) for tag in rule["payoff_tags"])
        if payoff <= 0:
            continue
        support = sum(flat_tags.get(tag, 0) for tag in rule["support_tags"])
        need = int(rule["min_support"])
        support_gaps.append((name, support, need, payoff))
    if support_gaps:
        print("\nSupport Checks:", file=sys.stderr)
        for name, support, need, payoff in support_gaps:
            status = "ok" if support >= need else "missing"
            print(f"  {name.replace('_', ' ').title():<28s}: {support}/{need} ({status}, payoffs {payoff})", file=sys.stderr)

    if plan_profile:
        required_tags: dict[str, int] = dict(plan_profile.get("required_tags", {}))
        package_profile = choose_active_packages(plan_profile, nonlands, tag_index)
        primary = package_profile.get("primary_plan")
        secondary = package_profile.get("secondary_plan")
        if primary or secondary:
            label = primary.replace("_", " ").title() if primary else "None"
            if secondary:
                label += f" + {secondary.replace('_', ' ').title()}"
            print("\nTheme Lock:", file=sys.stderr)
            print(f"  Active Packages             : {label}", file=sys.stderr)
        if required_tags:
            print("\nPlan Checks:", file=sys.stderr)
            for tag, need in sorted(required_tags.items()):
                have = flat_tags.get(tag, 0)
                status = "ok" if have >= need else "missing"
                print(f"  {tag.replace('_', ' ').title():<28s}: {have}/{need} ({status})", file=sys.stderr)
        plan_summary = plan_component_summary(flat_tags, plan_profile, package_profile)
        if plan_summary["components"]:
            print("\nEngine Checks:", file=sys.stderr)
            for label, have, need, ok in plan_summary["components"]:
                status = "ok" if ok else "missing"
                print(f"  {label.replace('_', ' ').title():<28s}: {have}/{need} ({status})", file=sys.stderr)

        # Engine flow chain analysis
        primary_plan_name = package_profile.get("primary_plan") or ""
        if primary_plan_name and primary_plan_name in ENGINE_FLOWS:
            ef = validate_engine_flow(flat_tags, primary_plan_name, plan_profile)
            print("\nEngine Flow Chain:", file=sys.stderr)
            for tier_name, score in ef["tier_scores"].items():
                bar_len = int(score * 10)
                bar = "█" * bar_len + "░" * (10 - bar_len)
                pct = int(score * 100)
                marker = " ← CRITICAL GAP" if tier_name == ef["critical_gap"] else ""
                print(f"  {tier_name.capitalize():<10s}: [{bar}] {pct:3d}%{marker}", file=sys.stderr)
            overall_pct = int(ef["overall_score"] * 100)
            print(f"  {'Overall':<10s}: {overall_pct}% chain completion", file=sys.stderr)

        # Win condition availability
        wc_results = detect_win_conditions([c["name"] for c in nonlands], flat_tags)
        available_wc = [w for w in wc_results if w["available"]]
        print("\nWin Conditions:", file=sys.stderr)
        if available_wc:
            for wc in available_wc:
                print(f"  [OK] {wc['name'].replace('_', ' ').title():<22s}: {wc['notes']}", file=sys.stderr)
        else:
            print("  [!!] No clear win condition detected — add finishers or combo pieces", file=sys.stderr)
        missing_wc = [w for w in wc_results if not w["available"]]
        if missing_wc:
            for wc in missing_wc[:3]:  # show top 3 missing paths
                print(f"  [  ] {wc['name'].replace('_', ' ').title():<22s}: {wc['description']}", file=sys.stderr)

    # Tribe analysis
    tribe_counter: Counter = Counter()
    for card in nonlands:
        for sub in get_subtypes(card):
            tribe_counter[sub] += 1
    main_tribes = [(t, c) for t, c in tribe_counter.most_common(5) if c >= 2]
    if main_tribes:
        print("\nTribal Composition:", file=sys.stderr)
        for tribe, count in main_tribes:
            print(f"  {tribe:<20s}: {count}", file=sys.stderr)

    print(f"\nLand Count  : {len(lands)}", file=sys.stderr)
    avg_power = sum(score_power(c) for c in nonlands) / max(len(nonlands), 1)
    print(f"Avg Power   : {avg_power:.2f}/10.0", file=sys.stderr)
    liability_counts: Counter = Counter()
    risky_cards: list[tuple[float, str]] = []
    for card in nonlands:
        flags = detect_liability_flags(card)
        if not flags:
            continue
        liability_counts.update(flags)
        risky_cards.append((liability_penalty(card), card["name"]))
    if liability_counts:
        print("\nLiability Flags:", file=sys.stderr)
        for flag, count in liability_counts.most_common():
            print(f"  {flag.replace('_', ' ').title():<28s}: {count}", file=sys.stderr)
        print("  Risky Cards                  : " + ", ".join(name for _score, name in sorted(risky_cards, reverse=True)[:5]), file=sys.stderr)
    print(f"{'─'*w}\n", file=sys.stderr)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_colors(color_str: str) -> set[str]:
    """Parse 'W,B' or 'WB' or 'white,black' into {'W','B'}."""
    color_map = {
        "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
        "w": "W", "u": "U", "b": "B", "r": "R", "g": "G",
    }
    colors: set[str] = set()
    parts = re.split(r"[,\s]+", color_str.strip().lower())
    for p in parts:
        p = p.strip()
        if p in color_map:
            colors.add(color_map[p])
        elif p.upper() in "WUBRG":
            colors.add(p.upper())
    return colors


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Procedurally generate a 100-card MTG Commander deck.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--commander", default="",
                        help="Commander name (required unless --list-commanders)")
    parser.add_argument("--list-commanders", action="store_true",
                        help="Print all available commanders and exit")
    parser.add_argument("--archetype", default="midrange",
                        choices=["aggro", "midrange", "control", "combo"],
                        help="Deck archetype (default: midrange)")
    parser.add_argument("--strategy", default="",
                        help="Additional strategy keyword(s); auto-detected from commander")
    parser.add_argument("--ignore-tribal", action="store_true",
                        help="Disable automatic tribal inference from commander subtypes")
    parser.add_argument("--max-rarity", default="mythic",
                        choices=["common", "uncommon", "rare", "mythic"],
                        help="Highest allowed rarity (default: mythic)")
    parser.add_argument("--output", default="",
                        help="Output file path (default: print to stdout)")
    parser.add_argument("--seed", type=int, default=None,
                        help="RNG seed for reproducibility")
    parser.add_argument("--no-evolve", action="store_true",
                        help="Skip evolutionary refinement (faster, lower quality)")
    parser.add_argument("--generations", type=int, default=200,
                        help="Evolutionary refinement generations (default: 200)")
    parser.add_argument("--diversity", type=float, default=1.0,
                        help="Diversity/noise level 0.0–3.0 (default: 1.0)")
    parser.add_argument("--candidate-decks", type=int, default=6,
                        help="Number of candidate deck shapes to explore before selecting the best (default: 6)")

    args = parser.parse_args()

    # ── Load database ────────────────────────────────────────────────────────
    print(f"Loading card database from {CARDS_DIR}...", file=sys.stderr)
    db = load_card_database()
    if not db:
        sys.exit("No cards loaded. Run fetch_commander.py first.")
    print(f"  Loaded {len(db)} cards.", file=sys.stderr)

    # ── List commanders and exit ─────────────────────────────────────────────
    if args.list_commanders:
        commanders = get_all_commanders(db)
        for c in commanders:
            ci = "".join(sorted(get_color_identity(c)))
            print(f"{c['name']:50s}  [{ci}]  {c.get('type_line','')}")
        print(f"\n{len(commanders)} commanders available.", file=sys.stderr)
        return

    if not args.commander:
        sys.exit("Error: --commander is required. Use --list-commanders to see options.")

    # ── Resolve commander ────────────────────────────────────────────────────
    commander = db.get(args.commander)
    if commander is None:
        # Case-insensitive fallback
        lower = args.commander.lower()
        commander = next((c for c in db.values() if c.get("name", "").lower() == lower), None)
    if commander is None:
        sys.exit(f"Error: commander '{args.commander}' not found in database.")
    if not is_commander_eligible(commander):
        sys.exit(f"Error: '{commander['name']}' is not a legendary creature or planeswalker.")

    colors = get_color_identity(commander)
    print(f"Commander: {commander['name']}  [{' '.join(sorted(colors))}]", file=sys.stderr)
    auto = commander_auto_strategy(commander, ignore_tribal=args.ignore_tribal)
    plan_profile = infer_commander_plan(commander)
    if args.ignore_tribal:
        plan_profile = remove_tribal_plan_bias(plan_profile)
    plan_profile = apply_strategy_tribal_mode(plan_profile, args.strategy)
    if auto:
        print(f"  Auto-strategy: {auto}", file=sys.stderr)
    if plan_profile.get("plans"):
        print(f"  Inferred plans: {', '.join(sorted(plan_profile['plans']))}", file=sys.stderr)

    if args.seed is not None:
        random.seed(args.seed)

    archetype  = args.archetype
    cfg        = ARCHETYPE_CONFIG[archetype]
    land_count = cfg["land_count"]
    nonland_slots = COMMANDER_MAIN_SIZE - land_count   # 99 - lands

    # ── Build synergy tag index ──────────────────────────────────────────────
    print("Classifying cards...", file=sys.stderr)
    # Merge synergy tags with functional role tags (wincon, ramp, draw, removal etc.)
    # so that ENGINE_FLOWS and WIN_CONDITION_REGISTRY can reference both vocabularies.
    tag_index: dict[str, frozenset[str]] = {
        name: detect_synergy_tags(card) | frozenset(classify_roles(card))
        for name, card in db.items()
    }

    # ── Separate lands / nonlands, filter by color identity ──────────────────
    commander_name_for_filter = commander.get("name") if commander else None
    all_nonlands = [
        card for card in db.values()
        if not is_land(card)
        and fits_colors(card, colors)
        and card.get("name") != commander_name_for_filter  # commander lives in command zone
    ]
    all_lands = [card for card in db.values() if is_land(card)]
    usable_lands = [
        land for land in all_lands
        if fits_colors(land, colors)   # must be legal in this deck's color identity
        and (
            (land_produces(land) & colors) or
            ("Basic" in (land.get("type_line") or "") and not land_produces(land))
        )
    ]
    print(f"  {len(all_nonlands)} nonland candidates, {len(usable_lands)} land candidates",
          file=sys.stderr)

    # ── Select nonlands ──────────────────────────────────────────────────────
    print(f"Selecting {nonland_slots} nonland cards ({archetype})...", file=sys.stderr)
    print(f"Exploring {args.candidate_decks} candidate deck shapes...", file=sys.stderr)
    selected_nonlands, land_count = generate_commander_candidates(
        all_nonlands, db, tag_index, archetype, colors,
        args.strategy, args.max_rarity, commander,
        diversity=args.diversity,
        generations=args.generations,
        no_evolve=args.no_evolve,
        plan_profile=plan_profile,
        num_candidates=args.candidate_decks,
        ignore_tribal=args.ignore_tribal,
    )
    nonland_slots = COMMANDER_MAIN_SIZE - land_count
    print(f"Selected candidate with {land_count} lands from quality-diversity archive...", file=sys.stderr)

    # ── Build mana base ──────────────────────────────────────────────────────
    print("Building mana base...", file=sys.stderr)
    _plan_tags_for_mana = frozenset(plan_profile.get("required_tags", {}).keys()) if plan_profile else frozenset()
    selected_lands = build_mana_base(selected_nonlands, usable_lands, colors, land_count, plan_tags=_plan_tags_for_mana)

    # ── Analysis ─────────────────────────────────────────────────────────────
    print_analysis(selected_nonlands, selected_lands, archetype, db, tag_index, plan_profile=plan_profile)
    sim = simulate_commander_goldfish(
        selected_nonlands, commander, land_count, tag_index,
        plan_profile=plan_profile,
    )
    color_pressure = estimate_color_pressure(selected_nonlands, colors, land_count)
    print(
        f"Goldfish    : first play {sim['mean_first_play_turn']:.1f}, "
        f"mana spent {sim['mean_mana_spent']:.1f}, "
        f"commander on-curve {sim['commander_on_curve_rate']:.0%}, "
        f"dead hands {sim['dead_hand_rate']:.0%}, "
        f"pair assembly {sim['pair_assembly_rate']:.0%}, "
        f"engine complete {sim['engine_completion_rate']:.0%}, "
        f"finisher seen {sim['finisher_seen_rate']:.0%}",
        file=sys.stderr,
    )
    print(
        f"Mana Math   : color score {color_pressure['color_score']:.2f}, "
        f"source shortage {color_pressure['shortage']:.1f}, "
        f"early untapped pressure {color_pressure['untapped_pressure']:.0%}",
        file=sys.stderr,
    )

    # ── Output ───────────────────────────────────────────────────────────────
    deck_text = format_commander(commander, selected_nonlands, selected_lands)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(deck_text)
        print(f"Deck written to: {args.output}", file=sys.stderr)
    else:
        print(deck_text)


# ══════════════════════════════════════════════════════════════════════════════
# SUBPROCESS / PYPY BRIDGE
# ══════════════════════════════════════════════════════════════════════════════

def _json_safe(obj):
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (frozenset, set)):
        return sorted(_json_safe(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def generate_deck(params: dict, progress_cb=None) -> dict:
    arch = params["archetype"]
    strat = params.get("strategy", "")
    rarity = params.get("max_rarity", "mythic")
    seed = params.get("seed")
    no_evo = params.get("no_evolve", False)
    gens = params.get("generations", 200)
    diversity = params.get("diversity", 1.0)
    commander_name = params["commander_name"]
    candidate_decks = params.get("candidate_decks", 6)
    strict_tribal = params.get("strict_tribal", False)
    strict_tribal_type: str | None = params.get("strict_tribal_type") or None
    ignore_tribal = params.get("ignore_tribal", False)
    if strict_tribal:
        ignore_tribal = False

    if seed is not None:
        random.seed(seed)

    cfg = ARCHETYPE_CONFIG[arch]
    land_override = params.get("land_override")

    def _p(msg, pct):
        if progress_cb:
            progress_cb(msg, pct)

    _p("Loading Commander card database…", 5)
    db = load_card_database()

    commander = db.get(commander_name)
    if commander is None:
        lower = commander_name.lower()
        commander = next((c for c in db.values() if c.get("name", "").lower() == lower), None)
    if commander is None:
        raise ValueError(f"Commander '{commander_name}' not found in database.")

    colors = get_color_identity(commander) or {"C"}
    auto = commander_auto_strategy(commander, ignore_tribal=ignore_tribal)
    plan_profile = infer_commander_plan(commander)
    if ignore_tribal:
        plan_profile = remove_tribal_plan_bias(plan_profile)
    plan_profile = apply_strategy_tribal_mode(plan_profile, strat)

    # If the user specified a tribe override, inject it into the plan profile
    # so all downstream scoring treats it as the primary tribe.
    if strict_tribal and strict_tribal_type:
        plan_profile = dict(plan_profile)
        plan_profile["primary_tribe"] = strict_tribal_type
        tribe_tag = f"tribe_{strict_tribal_type}"
        required_tags = dict(plan_profile.get("required_tags", {}))
        required_tags[tribe_tag] = max(required_tags.get(tribe_tag, 0), 20)
        plan_profile["required_tags"] = required_tags
        plans = set(plan_profile.get("plans", frozenset()))
        plans.add("tribal_synergy")
        plan_profile["plans"] = frozenset(plans)

    _p(f"Classifying {len(db):,} cards…", 15)
    tag_index = {
        name: detect_synergy_tags(card) | frozenset(classify_roles(card))
        for name, card in db.items()
    }

    commander_filter_name = commander.get("name")
    all_nonlands = [
        card for card in db.values()
        if not is_land(card)
        and fits_colors(card, colors)
        and card.get("name") != commander_filter_name
    ]
    all_lands = [card for card in db.values() if is_land(card)]
    usable_lands = [
        land for land in all_lands
        if fits_colors(land, colors)
        and (
            (land_produces(land) & colors) or
            ("Basic" in (land.get("type_line") or "") and not land_produces(land))
        )
    ]

    if land_override is not None:
        land_count = int(land_override)
        nonland_slots = COMMANDER_MAIN_SIZE - land_count
        _p(f"Selecting nonland cards ({nonland_slots} slots)…", 30)
        selected_nonlands = select_nonlands(
            all_nonlands, db, tag_index, arch, colors,
            strat, nonland_slots, rarity,
            diversity=diversity,
            commander=commander,
            plan_profile=plan_profile,
            strict_tribal=strict_tribal,
            ignore_tribal=ignore_tribal,
        )
        strat_words = list({
            *extract_strategy_terms(strat),
            *extract_strategy_terms(auto),
        } - {""})
        if not no_evo:
            _p(f"Evolving deck ({gens} generations)…", 55)
            selected_nonlands = evolutionary_refine(
                selected_nonlands, all_nonlands, db, tag_index, arch, gens,
                max_cmc=cfg.get("max_cmc", 99),
                strategy_words=strat_words,
                diversity=diversity,
                commander=commander,
                land_count=land_count,
                plan_profile=plan_profile,
                strict_tribal=strict_tribal,
            )
    else:
        _p(f"Selecting nonland cards (~{COMMANDER_MAIN_SIZE - cfg['land_count']} slots)…", 30)
        _p(f"Exploring {candidate_decks} candidate deck shapes…", 40)
        selected_nonlands, land_count = generate_commander_candidates(
            all_nonlands, db, tag_index, arch, colors,
            strat, rarity, commander,
            diversity=diversity,
            generations=gens,
            no_evolve=no_evo,
            plan_profile=plan_profile,
            num_candidates=candidate_decks,
            strict_tribal=strict_tribal,
            ignore_tribal=ignore_tribal,
        )

    _p("Building mana base…", 85)
    _plan_tags_for_mana = frozenset(plan_profile.get("required_tags", {}).keys()) if plan_profile else frozenset()
    selected_lands = build_mana_base(selected_nonlands, usable_lands, colors, land_count, plan_tags=_plan_tags_for_mana)

    _p("Assembling result…", 95)

    curve = dict(Counter(min(int(get_cmc(c)), 7) for c in selected_nonlands))
    roles_raw: Counter = Counter()
    for card in selected_nonlands:
        for role in set(classify_roles(card)):
            roles_raw[role] += 1

    pip_totals: dict[str, int] = {"W": 0, "U": 0, "B": 0, "R": 0, "G": 0}
    for card in selected_nonlands:
        mc = card.get("mana_cost") or ""
        for color, val in count_pips(mc).items():
            pip_totals[color] += val

    flat_tags: Counter = Counter()
    for name in {c["name"] for c in selected_nonlands}:
        for tag in tag_index.get(name, frozenset()):
            flat_tags[tag] += 1

    tribe_counter: Counter = Counter()
    for card in selected_nonlands:
        for sub in get_subtypes(card):
            tribe_counter[sub] += 1
    synergy_score, synergy_per_card = compute_synergy_rating(
        selected_nonlands, db, tag_index, plan_profile=plan_profile
    )

    return {
        "mode": "commander",
        "commander": commander,
        "nonlands": selected_nonlands,
        "lands": selected_lands,
        "curve": curve,
        "curve_targets": cfg["curve_targets"],
        "roles": dict(roles_raw),
        "pips": {c: v for c, v in pip_totals.items() if v > 0},
        "synergies": [
            [t, c] for t, c in flat_tags.most_common()
            if is_reportable_synergy(t, c, flat_tags)
        ],
        "tribes": [[t, c] for t, c in tribe_counter.most_common(8) if c >= 3],
        "synergy_score": synergy_score,
        "synergy_per_card": synergy_per_card,
        "avg_cmc": sum(get_cmc(c) for c in selected_nonlands) / max(len(selected_nonlands), 1),
        "avg_power": sum(score_power(c) for c in selected_nonlands) / max(len(selected_nonlands), 1),
        "deck_text": format_commander(commander, selected_nonlands, selected_lands),
        "total_cards": 1 + len(selected_nonlands) + len(selected_lands),
        "archetype": arch,
        "colors": sorted(colors),
        "land_count": len(selected_lands),
        "nonland_count": len(selected_nonlands),
        "card_count": 1 + len(set(c["name"] for c in selected_nonlands + selected_lands)),
    }


def _subprocess_main() -> None:
    import json as _json
    import traceback as _tb

    params = _json.loads(sys.stdin.read())

    def _progress(msg, pct):
        print(_json.dumps({"type": "progress", "msg": msg, "pct": pct}), flush=True)

    try:
        result = generate_deck(params, progress_cb=_progress)
        print(_json.dumps({"type": "result", "data": _json_safe(result)}), flush=True)
    except Exception:
        print(_json.dumps({"type": "error", "tb": _tb.format_exc()}), flush=True)


if __name__ == "__main__":
    if "--subprocess" in sys.argv:
        _subprocess_main()
    else:
        main()
