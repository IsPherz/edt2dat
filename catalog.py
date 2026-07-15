"""Declarative NpcId catalog (Arrowgene enum names → numeric ids)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_CATALOG = DATA_DIR / "npc_ids.json"


class NpcEntry(NamedTuple):
    name: str
    id: int

    @property
    def arc_name(self) -> str:
        return f"n{self.id:04d}.arc"


def load_catalog(path: Path = DEFAULT_CATALOG) -> tuple[NpcEntry, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(NpcEntry(n["name"], int(n["id"])) for n in raw["npcs"])


@lru_cache(maxsize=1)
def catalog() -> tuple[NpcEntry, ...]:
    return load_catalog()


def by_name(entries: tuple[NpcEntry, ...] | None = None) -> dict[str, NpcEntry]:
    src = entries if entries is not None else catalog()
    return {e.name: e for e in src}


def resolve(name_or_id: str, entries: tuple[NpcEntry, ...] | None = None) -> NpcEntry:
    """Resolve Arrowgene enum name (case-sensitive) or numeric id string."""
    src = entries if entries is not None else catalog()
    names = by_name(src)
    if name_or_id in names:
        return names[name_or_id]
    # case-insensitive fallback
    lower = {k.lower(): v for k, v in names.items()}
    if name_or_id.lower() in lower:
        return lower[name_or_id.lower()]
    try:
        nid = int(name_or_id, 0)
    except ValueError as e:
        raise KeyError(f"unknown NPC {name_or_id!r}") from e
    hits = [e for e in src if e.id == nid]
    if not hits:
        raise KeyError(f"no NpcId with id={nid}")
    # Prefer the first alphabetically if several enums share an id (rare).
    return sorted(hits, key=lambda e: e.name)[0]


def npc_rom_dir(game_root: Path) -> Path:
    return game_root / "nativePC" / "rom" / "npc"


def arc_path(game_root: Path, entry: NpcEntry) -> Path:
    return npc_rom_dir(game_root) / entry.arc_name


def with_arc_on_disk(
    game_root: Path, entries: tuple[NpcEntry, ...] | None = None
) -> tuple[NpcEntry, ...]:
    """Filter catalog to NPCs whose nXXXX.arc exists under the game install."""
    src = entries if entries is not None else catalog()
    root = npc_rom_dir(game_root)
    return tuple(e for e in src if (root / e.arc_name).is_file())
