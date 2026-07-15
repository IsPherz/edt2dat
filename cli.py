"""CLI: pick Arrowgene NpcId enum → write editdata .dat from game ROM."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .catalog import with_arc_on_disk
from .extract import default_arctool
from .pipeline import npc_to_editdata


def _default_appdata_edit() -> Path:
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "CAPCOM" / "Dragon's Dogma Online" / "edit"


def cmd_list(args: argparse.Namespace) -> int:
    entries = with_arc_on_disk(args.game) if args.game else None
    if entries is None:
        from .catalog import catalog

        entries = catalog()
        print(f"# all catalog entries ({len(entries)}); pass --game to filter by arc on disk")
    else:
        print(f"# {len(entries)} NPCs with nXXXX.arc under {args.game}")
    q = (args.query or "").lower()
    for e in entries:
        if q and q not in e.name.lower() and q not in str(e.id):
            continue
        print(f"{e.name}\t{e.id}\t{e.arc_name}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    result = npc_to_editdata(
        args.game,
        args.npc,
        author=args.author,
        comment=args.comment,
        arctool=args.arctool,
        write_comment=not args.no_comment,
        verbose=args.verbose,
    )
    out = args.output
    if out is None:
        out = Path(f"{result.entry.name}_from_edt.dat")
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.dat)

    print(f"NPC     {result.entry.name} (id={result.entry.id})")
    print(f"Arc     {result.arc}")
    print(f"Sex     {result.gender}  (from .edt)")
    print(f"Wrote   {out} ({len(result.dat)} bytes)")

    if args.slot is not None:
        edit_dir = args.appdata or _default_appdata_edit()
        slot = edit_dir / f"editdata{args.slot}.dat"
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.write_bytes(result.dat)
        print(f"Slot    {slot}")

    if args.verbose:
        print("Log:")
        print("\n".join(result.log))
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    from .gui import run_gui

    return run_gui()


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="edt2dat",
        description=(
            "Translate a DDON NPC look (NpcId → nXXXX.arc → .edt) into "
            "AppData editdata (.dat). Bundles male/female templates + uses ARCtool.\n"
            "Run with no arguments (or: gui) for the windowed UI."
        ),
    )
    ap.add_argument(
        "--arctool",
        type=Path,
        default=None,
        help=f"ARCtool.exe (default: {default_arctool()})",
    )
    sub = ap.add_subparsers(dest="cmd", required=False)

    p_gui = sub.add_parser("gui", help="Open the windowed UI (default if no command)")
    p_gui.set_defaults(func=cmd_gui)

    p_list = sub.add_parser("list", help="List NpcId enum names (optionally filter by disk)")
    p_list.add_argument(
        "--game",
        type=Path,
        default=None,
        help="DDON game root (folder that contains nativePC)",
    )
    p_list.add_argument("-q", "--query", default=None, help="filter by name/id substring")
    p_list.set_defaults(func=cmd_list)

    p_c = sub.add_parser("convert", help="NpcId → .dat")
    p_c.add_argument(
        "--game",
        type=Path,
        required=True,
        help="DDON game root (folder that contains nativePC)",
    )
    p_c.add_argument(
        "--npc",
        required=True,
        help="Arrowgene enum name (e.g. Nedo0, Mysial0, AdairDonnchadh1) or numeric id",
    )
    p_c.add_argument("-o", "--output", type=Path, default=None, help="output .dat path")
    p_c.add_argument(
        "--author",
        default=None,
        help="in-game Author column (default: yokaisparda)",
    )
    p_c.add_argument(
        "--comment",
        default=None,
        help="in-game Comment column (default: Arrowgene NPC enum name)",
    )
    p_c.add_argument(
        "--slot",
        type=int,
        default=None,
        help="also write AppData editdata{N}.dat",
    )
    p_c.add_argument(
        "--appdata",
        type=Path,
        default=None,
        help="edit folder (default: %%LOCALAPPDATA%%\\CAPCOM\\Dragon's Dogma Online\\edit)",
    )
    p_c.add_argument(
        "--no-comment",
        action="store_true",
        help="do not write Comment",
    )
    p_c.add_argument("-v", "--verbose", action="store_true")
    p_c.set_defaults(func=cmd_convert)

    return ap


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # No args → GUI for non-console users
    if not argv:
        return cmd_gui(argparse.Namespace())

    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "cmd", None):
        return cmd_gui(args)
    try:
        return args.func(args)
    except (KeyError, FileNotFoundError, RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
