"""Conflict check driven by an editable rules file (known-clashes.json)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from fcmh.ledger import Mod


@dataclass
class Clash:
    rule_id: str
    severity: str
    description: str
    advice: str
    mods: list[str]


def load_rules(path: str | Path | None = None) -> list[dict]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = resources.files("fcmh.data").joinpath("known-clashes.json").read_text(encoding="utf-8")
    data = json.loads(text)
    rules = data.get("rules", [])
    for rule in rules:
        for key in ("id", "members"):
            if key not in rule:
                raise ValueError(f"Clash rule is missing '{key}': {rule!r}")
        for member in rule["members"]:
            for pattern in member.get("patterns", []):
                re.compile(pattern)  # fail early on a broken pattern
    return rules


def _haystacks(mod: Mod) -> list[str]:
    name_of_file = Path(mod.file.replace("\\", "/")).name
    return [mod.name, name_of_file] + [f"tag:{t}" for t in mod.tags]


def matches(member: dict, mod: Mod) -> bool:
    for pattern in member.get("patterns", []):
        regex = re.compile(pattern, re.IGNORECASE)
        if any(regex.search(text) for text in _haystacks(mod)):
            return True
    return False


def find_clashes(mods: list[Mod], rules: list[dict]) -> list[Clash]:
    clashes: list[Clash] = []
    enabled = [m for m in mods if m.enabled]
    for rule in rules:
        hits: list[str] = []
        for mod in enabled:
            if any(matches(member, mod) for member in rule["members"]):
                hits.append(mod.name)
        if len(hits) > int(rule.get("max_enabled", 1)):
            clashes.append(Clash(
                rule_id=rule["id"],
                severity=rule.get("severity", "warning"),
                description=rule.get("description", ""),
                advice=rule.get("advice", ""),
                mods=hits,
            ))
    return clashes
