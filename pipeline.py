"""Compose: game NPC arc → editdata bytes (functional pipeline)."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from .catalog import NpcEntry, arc_path, resolve
from .edt_to_editdata import DEFAULT_AUTHOR, gender_from_edt, translate
from .extract import default_arctool, extract_first_edt

DATA_DIR = Path(__file__).resolve().parent / "data"
TEMPLATES = {
    "Male": DATA_DIR / "templates" / "male.dat",
    "Female": DATA_DIR / "templates" / "female.dat",
}


class TranslateResult(NamedTuple):
    entry: NpcEntry
    gender: str
    edt: bytes
    dat: bytes
    log: tuple[str, ...]
    arc: Path


def load_template(gender: str) -> bytes:
    path = TEMPLATES[gender]
    if not path.is_file():
        raise FileNotFoundError(f"bundled template missing: {path}")
    return path.read_bytes()


def npc_to_editdata(
    game_root: Path,
    name_or_id: str,
    *,
    author: str | None = None,
    comment: str | None = None,
    display_name: str | None = None,
    arctool: Path | None = None,
    write_comment: bool = True,
    verbose: bool = False,
) -> TranslateResult:
    """
    Resolve NpcId → extract first .edt from nXXXX.arc → inject into sex-matched
    bundled template. Sex always taken from .edt @0x14.

    In-game load list: Author column = ``author`` (default yokaisparda);
    Comment column = ``comment`` / ``display_name`` / Arrowgene enum name.
    """
    entry = resolve(name_or_id)
    arc = arc_path(game_root, entry)
    edt = extract_first_edt(arc, arctool=arctool or default_arctool())
    gender = gender_from_edt(edt)
    template = load_template(gender)
    author_text = author if author is not None else DEFAULT_AUTHOR
    if comment is not None:
        comment_text = comment
    elif display_name is not None:
        comment_text = display_name
    else:
        comment_text = entry.name
    dat, log = translate(
        edt,
        template,
        author=author_text,
        comment=comment_text,
        gender=gender,
        write_comment=write_comment,
        verbose=verbose,
    )
    return TranslateResult(
        entry=entry,
        gender=gender,
        edt=edt,
        dat=bytes(dat),
        log=tuple(log),
        arc=arc,
    )
