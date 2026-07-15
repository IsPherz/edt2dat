"""Extract the first rCharacterEdit (.edt) from an NPC .arc via ARCtool."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

EDT_HASH = ".3E894FE7"
EDT_EXT = ".edt"

_TOOL_DIR = Path(__file__).resolve().parent
_DEFAULT_ARCTOOL = _TOOL_DIR / "ARCtool.exe"


def default_arctool() -> Path:
    """ARCtool.exe shipped next to this tool (same folder as the launch bat)."""
    return _DEFAULT_ARCTOOL


def _rank_edt(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    prefer00 = 0 if "_00" in name else 1
    return (prefer00, name)


def pick_first_edt(paths: list[Path]) -> Path:
    if not paths:
        raise FileNotFoundError("no .edt / *.3E894FE7 in archive")
    return sorted(paths, key=_rank_edt)[0]


def find_edts(unpack_root: Path) -> list[Path]:
    hits = list(unpack_root.rglob(f"*{EDT_HASH}"))
    hits += [p for p in unpack_root.rglob(f"*{EDT_EXT}") if p not in hits]
    return hits


def unpack_arc(arc: Path, dest: Path, *, arctool: Path | None = None) -> Path:
    tool = arctool or default_arctool()
    if not tool.is_file():
        raise FileNotFoundError(
            f"ARCtool not found: {tool}\n"
            f"Place ARCtool.exe in: {_TOOL_DIR}"
        )
    if not arc.is_file():
        raise FileNotFoundError(f"NPC arc not found: {arc}")

    dest.mkdir(parents=True, exist_ok=True)
    local_arc = dest / arc.name
    shutil.copy2(arc, local_arc)

    cmd = [
        str(tool),
        "-ddo",
        "-texRE6",
        "-alwayscomp",
        "-pc",
        "-txt",
        "-v",
        "7",
        local_arc.name,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(dest),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ARCtool failed ({proc.returncode}): {arc.name}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return dest


def extract_first_edt(
    arc: Path, *, arctool: Path | None = None, work_dir: Path | None = None
) -> bytes:
    def _run(root: Path) -> bytes:
        unpack_arc(arc, root, arctool=arctool)
        return pick_first_edt(find_edts(root)).read_bytes()

    if work_dir is not None:
        return _run(work_dir)

    with tempfile.TemporaryDirectory(prefix="edt2dat_") as tmp:
        return _run(Path(tmp))
