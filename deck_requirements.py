from __future__ import annotations

import re
from collections import Counter

CARD_TYPES = {
    "artifact", "battle", "creature", "enchantment", "instant",
    "land", "planeswalker", "sorcery",
}

CREATURE_TYPES = {
    "advisor", "angel", "archer", "artificer", "assassin", "assembly-worker",
    "bat", "bear", "beast", "berserker", "bird", "cat", "cleric", "construct",
    "coward", "crab", "demon", "devil", "dinosaur", "dragon", "druid", "dryad",
    "dwarf", "elemental", "elf", "faerie", "fish", "fox", "fungus", "giant",
    "gnome", "goat", "goblin", "god", "golem", "griffin", "horror", "horse",
    "human", "hydra", "insect", "kavu", "knight", "kobold", "kor", "leviathan",
    "lizard", "merfolk", "minotaur", "monk", "mouse", "mutant", "ninja",
    "nightmare", "ooze", "orc", "pegasus", "pirate", "plant", "rabbit", "rat",
    "rebel", "rhino", "rogue", "samurai", "saproling", "serpent", "shaman",
    "shapeshifter", "sliver", "snake", "soldier", "spider", "spirit", "squirrel",
    "treefolk", "vampire", "warlock", "warrior", "wizard", "wolf", "wurm",
    "zombie",
}

ROLE_SOFT_CAPS = {
    "counterspell": 6,
    "sweeper": 4,
    "tutor": 5,
    "removal": 14,
}

TAG_SOFT_CAPS = {
    "sac_outlet": 4,
    "token_payoff": 4,
    "artifact_payoff": 4,
    "enchantment_payoff": 4,
    "spells_payoff": 7,
    "graveyard_payoff": 6,
    "etb_payoff": 5,
}

CONFLICT_RULES = (
    ("voltron_enabler", "token_maker", 5, 5, 2.4),
    ("voltron_enabler", "anthem", 5, 3, 2.0),
    ("artifact_payoff", "spells_payoff", 4, 5, 1.8),
)


def _type_words(card: dict) -> set[str]:
    words: set[str] = set()
    type_line = (card.get("type_line") or "").replace("—", " ")
    for token in re.split(r"[^A-Za-z]+", type_line.lower()):
        if token in CARD_TYPES:
            words.add(token)
    return words


def infer_card_requirements(card: dict) -> tuple[dict[str, object], ...]:
    oracle = (card.get("oracle_text") or "").lower()
    keywords = {k.lower() for k in (card.get("keywords") or [])}
    reqs: list[dict[str, object]] = []

    if "learn" in oracle or "learn" in keywords:
        reqs.append({"kind": "mechanic_disabled", "mechanic": "learn", "penalty": 5.5})

    if re.search(r"\bmulticolored creature\b", oracle):
        reqs.append({"kind": "multicolor_creature_count", "min": 6, "penalty": 3.8})

    if "modified creature" in oracle or "modified creatures" in oracle:
        reqs.append({"kind": "tag_count", "tags": ("modified_enabler",), "min": 6, "penalty": 3.0})

    if re.search(r"\bparty\b", oracle):
        reqs.append({"kind": "tag_count", "tags": ("party_cleric", "party_rogue", "party_warrior", "party_wizard"), "min": 3, "penalty": 2.5})

    subtype_patterns = [
        (r"reveal (?:a|an) ([a-z]+) card", 7, 3.8),
        (r"if you control (?:a|an|another) ([a-z]+)", 6, 3.0),
        (r"for each ([a-z]+) you control", 6, 2.6),
        (r"sacrifice (?:a|an) ([a-z]+)", 5, 2.6),
    ]
    for pattern, minimum, penalty in subtype_patterns:
        for raw in re.findall(pattern, oracle):
            token = raw.strip().lower()
            if token in CARD_TYPES:
                reqs.append({"kind": "type_count", "types": (token,), "min": minimum, "penalty": penalty})
            elif token in CREATURE_TYPES:
                reqs.append({"kind": "subtype_count", "subtypes": (token.title(),), "min": minimum, "penalty": penalty})

    if re.search(r"legendary creature cards? you own|your commander|commander creatures? you own", oracle):
        reqs.append({"kind": "commander_text", "penalty": 3.5})

    return tuple(reqs)


def build_deck_state(
    cards: list[dict],
    tag_index: dict[str, frozenset[str]],
    classify_roles,
    get_subtypes,
    commander: dict | None = None,
) -> dict[str, object]:
    subtype_counts: Counter = Counter()
    type_counts: Counter = Counter()
    role_counts: Counter = Counter()
    tag_counts: Counter = Counter()
    keyword_counts: Counter = Counter()
    multicolor_creatures = 0

    all_cards = list(cards)
    if commander is not None:
        all_cards.append(commander)

    for card in all_cards:
        for subtype in get_subtypes(card):
            subtype_counts[subtype] += 1
        for type_word in _type_words(card):
            type_counts[type_word] += 1
        for role in set(classify_roles(card)):
            role_counts[role] += 1
        for tag in tag_index.get(card["name"], frozenset()):
            tag_counts[tag] += 1
        for keyword in (card.get("keywords") or []):
            keyword_counts[str(keyword).lower()] += 1
        if "Creature" in (card.get("type_line") or "") and len(card.get("color_identity") or []) >= 2:
            multicolor_creatures += 1

    return {
        "subtype_counts": subtype_counts,
        "type_counts": type_counts,
        "role_counts": role_counts,
        "tag_counts": tag_counts,
        "keyword_counts": keyword_counts,
        "multicolor_creatures": multicolor_creatures,
    }


def evaluate_card_requirements(
    card: dict,
    deck_state: dict[str, object],
    format_name: str = "commander",
) -> tuple[float, list[str]]:
    penalty = 0.0
    unmet: list[str] = []
    for req in infer_card_requirements(card):
        kind = req["kind"]
        req_penalty = float(req.get("penalty", 2.0))
        if kind == "mechanic_disabled":
            if req.get("mechanic") == "learn":
                penalty += req_penalty
                unmet.append("learn_without_lessons")
        elif kind == "multicolor_creature_count":
            have = int(deck_state["multicolor_creatures"])
            need = int(req["min"])
            if have < need:
                penalty += req_penalty * (need - have) / need
                unmet.append(f"multicolor_creatures<{need}")
        elif kind == "subtype_count":
            have = sum(int(deck_state["subtype_counts"].get(sub, 0)) for sub in req["subtypes"])
            need = int(req["min"])
            if have < need:
                penalty += req_penalty * (need - have) / need
                unmet.append(f"subtype<{need}:{','.join(req['subtypes'])}")
        elif kind == "type_count":
            have = sum(int(deck_state["type_counts"].get(t, 0)) for t in req["types"])
            need = int(req["min"])
            if have < need:
                penalty += req_penalty * (need - have) / need
                unmet.append(f"type<{need}:{','.join(req['types'])}")
        elif kind == "tag_count":
            have = sum(int(deck_state["tag_counts"].get(tag, 0)) for tag in req["tags"])
            need = int(req["min"])
            if have < need:
                penalty += req_penalty * (need - have) / need
                unmet.append(f"tag<{need}:{','.join(req['tags'])}")
        elif kind == "commander_text":
            penalty += req_penalty
            unmet.append("commander_only_text")
    return penalty, unmet


def commander_role_penalty(card: dict) -> float:
    type_line = (card.get("type_line") or "")
    oracle = (card.get("oracle_text") or "").lower()
    if "Legendary" not in type_line or "Creature" not in type_line:
        return 0.0
    penalty = 0.0
    if "your commander" in oracle or "can be your commander" in oracle:
        penalty += 2.2
    if re.search(r"commander creatures? you own|command zone", oracle):
        penalty += 2.8
    return penalty


def diminishing_returns_penalty(
    deck_state: dict[str, object],
    redundancy_targets: dict[str, int] | None = None,
) -> float:
    redundancy_targets = redundancy_targets or {}
    penalty = 0.0
    tag_counts: Counter = deck_state["tag_counts"]
    role_counts: Counter = deck_state["role_counts"]

    for tag, soft_cap in TAG_SOFT_CAPS.items():
        have = int(tag_counts.get(tag, 0))
        if have > soft_cap:
            penalty += (have - soft_cap) * 0.35

    for role, soft_cap in ROLE_SOFT_CAPS.items():
        have = int(role_counts.get(role, 0))
        if have > soft_cap:
            penalty += (have - soft_cap) * 0.25

    for tag, target in redundancy_targets.items():
        have = int(tag_counts.get(tag, 0))
        slack = max(1, target // 3)
        if have > target + slack:
            penalty += (have - (target + slack)) * (0.28 if tag in TAG_SOFT_CAPS else 0.16)

    for tag_a, tag_b, min_a, min_b, weight in CONFLICT_RULES:
        have_a = int(tag_counts.get(tag_a, 0))
        have_b = int(tag_counts.get(tag_b, 0))
        if have_a >= min_a and have_b >= min_b:
            penalty += weight

    return penalty


def deck_requirement_penalty(
    cards: list[dict],
    tag_index: dict[str, frozenset[str]],
    classify_roles,
    get_subtypes,
    redundancy_targets: dict[str, int] | None = None,
    commander: dict | None = None,
    format_name: str = "commander",
) -> float:
    deck_state = build_deck_state(cards, tag_index, classify_roles, get_subtypes, commander=commander)
    penalty = 0.0
    for card in cards:
        card_penalty, _ = evaluate_card_requirements(card, deck_state, format_name=format_name)
        penalty += card_penalty
        penalty += commander_role_penalty(card)
    penalty += diminishing_returns_penalty(deck_state, redundancy_targets)
    return penalty / max(len(cards), 1)
