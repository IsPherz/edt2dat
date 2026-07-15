"""
Inject DDON NPC .edt morph floats into AppData editdataN.dat.

Reverse of editdata_to_edt.py. Uses Relative-to-Height layout.
Writes face H-31..H-1, body live slots, Eye/Nose/Mouth/Brow shape IDs
(4x u32 before Temple / H-31), Hair Color (.edt 0x4C → Height+0x3C),
Colors: Skin (0x48→H+0x38), Hair (0x4C→H+0x3C), Beard (0x50→H+0x40),
Brow (0x54→H+0x44), Eyes (0x58/0x5C→H+0x48/0x4C), Makeup (0x60→H+0x50).
Hair / beard / makeup *styles* are NOT written (UI↔file IDs unmapped; unsafe).
Style colors (including makeup color) still transfer. Comment keeps A#### hair asset id.
"""
from __future__ import annotations

import argparse
import struct
from pathlib import Path

MAGIC = b"EDT\x00"

# same map as editdata_to_edt.py
FACE_H_NEG: dict[int, int] = {
    31: 0x0065,
    30: 0x0073,
    29: 0x0081,
    28: 0x009D,
    27: 0x00E3,
    26: 0x00F1,
    25: 0x00FF,
    24: 0x008F,
    23: 0x0209,
    22: 0x01FB,
    21: 0x010D,
    20: 0x0145,
    19: 0x0153,
    18: 0x01A7,
    17: 0x01B5,
    16: 0x01C3,
    15: 0x01D1,
    14: 0x016F,
    13: 0x0161,
    12: 0x011B,
    11: 0x0129,
    10: 0x0137,
    9: 0x00AB,
    8: 0x00C7,
    7: 0x01DF,
    6: 0x01ED,
    5: 0x017D,
    4: 0x00D5,
    3: 0x00B9,
    2: 0x018B,
    1: 0x0199,
}

BODY_H_POS: list[tuple[int, int, tuple[float, float] | None, str]] = [
    # (H+, edt_off, dat_range_or_None, label)
    # dat_range None = copy .edt cur (clamp to edt min/max) — preferred for
    # sex-specific live slots. Non-None = UI-bridge into fixed male pack spans.
    (0, 0x02BF, None, "Head Size"),
    (1, 0x02E9, None, "Neck Length"),  # body#10; pack [-1.5,2.5] = editdata H+1
    (2, 0x02F7, None, "Neck Thickness/Width"),
    # 0x0305 pack is [0.83,1.30] = male Shoulder (editdata H+3), NOT Muscle.
    # Confirmed visually: Charles←Nedo max @0x0305 widened shoulders (2026-07-15).
    # Stub 0x0295 "UpperBodyScaleX" stays NPC-unused (~0.7).
    (3, 0x0305, None, "Shoulder Width"),
    (4, 0x0321, None, "Waist Size"),
    # Chest: female live @0x032F (Mysial); male ~1.0 unused. NOT stub 0x02B1.
    (5, 0x032F, None, "Chest Size"),
    (6, 0x033D, None, "Hand Size"),
    (7, 0x0367, None, "Hip Position"),  # pack [-9,3.5] = editdata H+7
    (8, 0x0375, None, "Hip Size"),
    (9, 0x039F, None, "Feet Size"),  # body#59; pack [-1.3,1.8] ≈ editdata H+9
    # Fat / Muscle live after Feet in .edt (body#24/#25), not in the early stubs.
    (10, 0x03AD, None, "Fat"),       # pack [-1,1] matches editdata H+10
    (11, 0x03BB, None, "Muscle"),    # pack [0,1] matches editdata H+11
]

HEIGHT_OFF = 0x025D
# Leave these H+ slots on the same-sex template (do not write from unused .edt):
# 12 Stance — no live NPC .edt source yet
SKIP_BODY_H = {12}


def find_height(buf: bytes) -> int:
    for i in range(0x100, 0x400):
        v = struct.unpack_from("<f", buf, i)[0]
        if 140.0 <= v <= 210.0:
            nxt = struct.unpack_from("<f", buf, i + 4)[0]
            if 0.5 < nxt < 3.0:
                return i
    raise ValueError("Height float not found in editdata")


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def via_ui(src: float, src_lo: float, src_hi: float, dst_lo: float, dst_hi: float) -> float:
    if src_hi <= src_lo:
        return dst_lo
    t = (src - src_lo) / (src_hi - src_lo)
    t = max(0.0, min(1.0, t))
    return dst_lo + t * (dst_hi - dst_lo)


def edt_shape_ids(edt: bytes) -> tuple[int, int, int, int]:
    """Eye/Nose/Mouth/Brow — 0-based file IDs (byte at .edt off+1)."""
    return edt[0x39], edt[0x3D], edt[0x41], edt[0x45]


def editdata_shape_ids(edt: bytes) -> tuple[int, int, int, int]:
    """File IDs in editdata mid order before Temple: Eye, Brow, Nose, Mouth.

    Nedo load A/B: writing .edt ENMB order showed UI Nose=Mouth, Mouth=Brow,
    Brow=Nose. Storage order is E,B,N,M (not cEditParam / .edt listing order).
    """
    eye, nose, mouth, brow = edt_shape_ids(edt)
    return eye, brow, nose, mouth


def preset_comment(edt: bytes) -> str:
    """Compact Comment code (max ~22 chars, no spaces).

    Shape numbers are IN-GAME UI indices: UI = file_byte + 1
    (.edt / assets are 0-based; creation grid shows 1-based).
    Hair A#### is still the raw .edt u16 (hr10NNNN), not UI#.
    """
    eye, nose, mouth, brow = edt_shape_ids(edt)
    hair = struct.unpack_from("<H", edt, 0x15)[0]
    code = f"E{eye + 1}N{nose + 1}M{mouth + 1}B{brow + 1}"
    hair_tag = f"A{hair}"
    if len(code) + len(hair_tag) <= 22:
        code += hair_tag
    return code


def inject_shape_presets(edt: bytes, editdata: bytearray, h: int) -> list[str]:
    """Write Eye/Brow/Nose/Mouth as 4x u32 immediately before Temple (H-31).

    Packed face floats begin at H-31; the four s32s before that are shape kits
    (0-based file IDs). Order in editdata is Eye, Brow, Nose, Mouth.
    """
    temple = h - 4 * 31
    ids = editdata_shape_ids(edt)
    labels = ("Eye Shape", "Brow Shape", "Nose Shape", "Mouth Shape")
    log: list[str] = []
    for i, (lab, new_v) in enumerate(zip(labels, ids)):
        abs_off = temple - 16 + 4 * i
        old = struct.unpack_from("<I", editdata, abs_off)[0]
        struct.pack_into("<I", editdata, abs_off, new_v)
        log.append(f"  {lab:28s} @0x{abs_off:04X}  {old:9d} -> {new_v:9d}  (UI {new_v + 1})")
    return log


def inject_palette_u32(edt: bytes, editdata: bytearray, h: int, *, edt_id_off: int, h_rel: int, label: str) -> str:
    """Write a 0-based palette index: .edt byte @ edt_id_off → editdata u32 @ H+h_rel."""
    abs_off = h + h_rel
    new_v = edt[edt_id_off]
    old = struct.unpack_from("<I", editdata, abs_off)[0]
    struct.pack_into("<I", editdata, abs_off, new_v)
    return f"  {label:28s} @0x{abs_off:04X}  {old:9d} -> {new_v:9d}"


def find_mhair_offset(editdata: bytes) -> int:
    """Absolute offset of mid-block mHair u32.

    Two male mid layouts exist:
      A) name\\0 + \"Male\"/\"Female\"\\0 + u8 sex + mHair…  (editdata6 / short name)
      B) name\\0 + shortName\\0 + u8 sex + mHair…           (editdata1 — Height stays aligned)
    Prefer A if gender word present; else B (skip second C-string, then sex).
    """
    mid = 0x138
    for word in (b"Female\x00", b"Male\x00"):
        i = editdata.find(word, mid, mid + 48)
        if i >= 0:
            return i + len(word) + 1  # skip sex u8
    p = mid
    while p < mid + 64 and editdata[p] != 0:
        p += 1
    if p >= mid + 64:
        raise ValueError("mid name not terminated")
    p += 1  # long-name NUL
    # optional short name (editdata1: \"Laios\" after \"Laios Touden\")
    if p < mid + 64 and editdata[p] != 0:
        while p < mid + 64 and editdata[p] != 0:
            p += 1
        p += 1
    elif p < mid + 64 and editdata[p] == 0:
        p += 1  # pad NUL (e7-style)
    return p + 1  # skip sex


def inject(edt: bytes, editdata: bytearray, *, verbose: bool = True) -> list[str]:
    if edt[:4] != MAGIC:
        raise ValueError(f"bad edt magic {edt[:4]!r}")
    h = find_height(bytes(editdata))
    log: list[str] = []

    def set_dat(abs_off: int, new_v: float, label: str) -> None:
        old = struct.unpack_from("<f", editdata, abs_off)[0]
        struct.pack_into("<f", editdata, abs_off, new_v)
        if abs(old - new_v) > 1e-5 or verbose:
            log.append(f"  {label:28s} @0x{abs_off:04X}  {old:9.4f} -> {new_v:9.4f}")

    # Shape kits before face floats (prevents template Eye=0 / first-of-list)
    for line in inject_shape_presets(edt, editdata, h):
        if verbose or "->" in line:
            log.append(line)

    # Colors (palette indices) — editdata offsets CONFIRMED A/B on editdata7.
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x49, h_rel=0x38, label="Skin Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x4D, h_rel=0x3C, label="Hair Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x51, h_rel=0x40, label="Beard Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x55, h_rel=0x44, label="Brow Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x59, h_rel=0x48, label="Eye Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x5D, h_rel=0x4C, label="Left Eye Color")
    )
    log.append(
        inject_palette_u32(edt, editdata, h, edt_id_off=0x61, h_rel=0x50, label="Makeup Color")
    )

    # Height
    height = struct.unpack_from("<f", edt, HEIGHT_OFF)[0]
    set_dat(h, height, "Height (cm)")

    # Face: copy edt cur → dat (same ranges)
    for d, off in sorted(FACE_H_NEG.items(), reverse=True):
        cur, mn, mx = struct.unpack_from("<fff", edt, off)
        set_dat(h - 4 * d, clamp(cur, mn, mx), f"Face H-{d}")

    # Body — only confirmed live slots; skip Shoulder/Chest/etc. (see SKIP_BODY_H)
    for k, off, dat_range, label in BODY_H_POS:
        if k in SKIP_BODY_H:
            continue
        cur, mn, mx = struct.unpack_from("<fff", edt, off)
        abs_off = h + 4 * (k + 1)  # H+0 = first float after Height
        if dat_range is None:
            # Prefer keeping the .edt cur when it already lives in player-like
            # units (Head/Waist/Hand/Hip/NeckW/Muscle). Clamp to edt min/max.
            new_v = clamp(cur, mn, mx)
        else:
            dlo, dhi = dat_range
            if abs(dlo - mn) < 1e-4 and abs(dhi - mx) < 1e-4:
                new_v = cur
            else:
                new_v = via_ui(cur, mn, mx, dlo, dhi)
            new_v = clamp(new_v, dlo, dhi)
        set_dat(abs_off, new_v, label)

    return log


def set_editdata_comment(editdata: bytearray, text: str) -> None:
    """Write Comment after 'Comment:' only.

    Do NOT write @0x88 — that slot is a short nickname (e.g. \"Laios\"), not the
    preset code. Stuffing E33N… there corrupts the male mid/UI layout.
    """
    raw = text.encode("ascii")
    if len(raw) > 22:
        raise ValueError(f"comment longer than 22 chars: {text!r}")
    label = editdata.find(b"Comment:")
    if label < 0:
        raise ValueError("Comment: label not found in editdata")
    val = label + len(b"Comment:")
    editdata[val : val + 64] = b"\x00" * 64
    editdata[val : val + len(raw)] = raw


def set_editdata_name(editdata: bytearray, name: str) -> None:
    """Overwrite display name @0x48, mid long name, mid short name, and @0x88 nickname.

    Preserves existing field widths so Height / morph alignment does not shift.
    Does not invent a \"Male\" mid word — keep the template's layout (e1-style
    short-name vs e6-style Male/Female).
    """
    raw = name.encode("ascii")
    if len(raw) > 31:
        raise ValueError(f"name too long: {name!r}")
    editdata[0x48 : 0x48 + 32] = b"\x00" * 32
    editdata[0x48 : 0x48 + len(raw)] = raw

    def _fit(field_len: int) -> bytes:
        """Pad with spaces so C-string length stays field_len (keeps mHair / Height)."""
        if field_len <= 0:
            return b""
        if len(raw) >= field_len:
            return raw[:field_len]
        return raw + b" " * (field_len - len(raw))

    # @0x88 short nickname (keep existing field width up to first NUL)
    early = 0x88
    e_end = early
    while e_end < early + 32 and editdata[e_end] != 0:
        e_end += 1
    e_len = e_end - early
    if e_len <= 0:
        e_len = min(len(raw), 15)
    editdata[early : early + e_len] = _fit(e_len)

    mid = 0x138
    end = mid
    while end < mid + 64 and editdata[end] != 0:
        end += 1
    old_len = end - mid
    if old_len <= 0:
        editdata[mid : mid + len(raw)] = raw
        editdata[mid + len(raw)] = 0
        return
    editdata[mid : mid + old_len] = _fit(old_len)

    # Second C-string after long name — short name on e1; skip if Male/Female
    p = mid + old_len + 1
    if editdata[p : p + 6] == b"Female" or editdata[p : p + 4] == b"Male":
        return
    if p < mid + 64 and editdata[p] != 0:
        s_end = p
        while s_end < mid + 64 and editdata[s_end] != 0:
            s_end += 1
        s_len = s_end - p
        editdata[p : p + s_len] = _fit(s_len)


def set_editdata_gender(editdata: bytearray, gender: str, *, author: str | None = None) -> None:
    """Rewrite Author/Gender/Comment meta block (display only)."""
    g = gender.strip().capitalize()
    if g not in ("Male", "Female"):
        raise ValueError("gender must be Male or Female")
    author_i = editdata.find(b"Author:")
    if author_i < 0:
        raise ValueError("Author: not found")
    nl = editdata.find(b"\n", author_i)
    if nl < 0:
        raise ValueError("Author line incomplete")
    if author is None:
        author_line = bytes(editdata[author_i:nl])
    else:
        author_line = b"Author:" + author.encode("ascii")
    comment_i = editdata.find(b"Comment:", nl)
    if comment_i < 0:
        raise ValueError("Comment: not found after Author")
    cval = comment_i + len(b"Comment:")
    end = cval
    while end < len(editdata) and editdata[end] != 0:
        end += 1
    comment_text = bytes(editdata[cval:end])
    block = author_line + b"\nGender:" + g.encode("ascii") + b"\nComment:" + comment_text + b"\x00"
    wipe = 0x180
    editdata[author_i : author_i + wipe] = b"\x00" * wipe
    editdata[author_i : author_i + len(block)] = block


def set_editdata_gender_flags(editdata: bytearray, gender: str) -> None:
    """Binary sex flag used by selector / editor (not the ASCII Gender: line).

    editdata5 Female vs editdata6 Male A/B:
      u32 @ 0x0110 = 1 Female / 0 Male

    NOTE: Height+0x50 is Makeup Color (palette u32), NOT sex. Early female/male
    probes had makeup 1 vs 0 and looked like a sex byte — do not write sex there.
    """
    g = gender.strip().capitalize()
    if g not in ("Male", "Female"):
        raise ValueError("gender must be Male or Female")
    sex = 1 if g == "Female" else 0
    struct.pack_into("<I", editdata, 0x110, sex)


def edt_gender_byte(edt: bytes) -> int:
    """0=Male, 1=Female at .edt 0x14."""
    return edt[0x14]


def gender_from_edt(edt: bytes) -> str:
    return "Female" if edt_gender_byte(edt) == 1 else "Male"


def translate(
    edt: bytes,
    template: bytes,
    *,
    name: str | None = None,
    gender: str | None = None,
    write_comment: bool = True,
    verbose: bool = True,
) -> tuple[bytearray, list[str]]:
    """Inject .edt into a copy of template editdata. Returns (dat, log lines)."""
    dat = bytearray(template)
    log = inject(edt, dat, verbose=verbose)
    sex = gender if gender is not None else gender_from_edt(edt)

    set_editdata_gender_flags(dat, sex)
    log.append(f"  Sex flag @0x110              -> {sex}")

    if name:
        set_editdata_name(dat, name)
        log.append(f"  Name                          -> {name}")

    set_editdata_gender(dat, sex, author=name)
    log.append(f"  Gender text                   -> {sex}  (edt 0x14={edt_gender_byte(edt)})")
    if name:
        log.append(f"  Author                        -> {name}")

    if write_comment:
        code = preset_comment(edt)
        set_editdata_comment(dat, code)
        log.append(f"  Comment                       -> {code}")

    set_editdata_gender_flags(dat, sex)
    return dat, log


def main() -> None:
    ap = argparse.ArgumentParser(description="Inject .edt morphs into editdataN.dat")
    ap.add_argument("edt", type=Path)
    ap.add_argument(
        "editdata",
        type=Path,
        help="template editdataN.dat — use a Female slot for female NPCs",
    )
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("-q", "--quiet", action="store_true")
    ap.add_argument("--name", type=str, default=None, help="slot display name")
    ap.add_argument(
        "--gender",
        type=str,
        default=None,
        help="Male|Female (default: from .edt byte 0x14)",
    )
    ap.add_argument(
        "--no-comment",
        action="store_true",
        help="do not overwrite Comment with E/N/M/B code",
    )
    args = ap.parse_args()

    edt = args.edt.read_bytes()
    dat, log = translate(
        edt,
        args.editdata.read_bytes(),
        name=args.name,
        gender=args.gender,
        write_comment=not args.no_comment,
        verbose=not args.quiet,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(dat)
    if not args.quiet:
        h = find_height(bytes(dat))
        print(f"Wrote {args.output} ({len(dat)} bytes)")
        print("Morph changes:")
        print("\n".join(log) if log else "  (none)")
        print()
        print(f"Verify: u32@0x110 (sex)={struct.unpack_from('<I', dat, 0x110)[0]}")
        eye, nose, mouth, brow = edt_shape_ids(edt)
        t = h - 4 * 31
        got = struct.unpack_from("<IIII", dat, t - 16)
        print(f"Preset Comment code: {preset_comment(edt)}")
        print(
            f"  Shapes .edt file/UI: Eye={eye}/{eye+1} Nose={nose}/{nose+1} "
            f"Mouth={mouth}/{mouth+1} Brow={brow}/{brow+1}"
        )
        print(f"  editdata order E,B,N,M before Temple@0x{t:04X}: {got}")
        print(
            f"  Skin Color .edt@0x49={edt[0x49]} -> H+0x38="
            f"{struct.unpack_from('<I', dat, h + 0x38)[0]}"
        )
        print(
            f"  Hair Color .edt@0x4D={edt[0x4D]} -> H+0x3C="
            f"{struct.unpack_from('<I', dat, h + 0x3C)[0]}"
        )
        print(
            f"  Beard Color .edt@0x51={edt[0x51]} -> H+0x40="
            f"{struct.unpack_from('<I', dat, h + 0x40)[0]}"
        )
        print(
            f"  Brow Color .edt@0x55={edt[0x55]} -> H+0x44="
            f"{struct.unpack_from('<I', dat, h + 0x44)[0]}"
        )
        print(
            f"  Eye Color .edt@0x59={edt[0x59]} -> H+0x48="
            f"{struct.unpack_from('<I', dat, h + 0x48)[0]}"
        )
        print(
            f"  Left Eye .edt@0x5D={edt[0x5D]} -> H+0x4C="
            f"{struct.unpack_from('<I', dat, h + 0x4C)[0]}"
        )
        print(
            f"  Makeup Color .edt@0x61={edt[0x61]} -> H+0x50="
            f"{struct.unpack_from('<I', dat, h + 0x50)[0]}"
        )
        hair_off = find_mhair_offset(bytes(dat))
        print(
            f"  Styles left on template: mHair@0x{hair_off:04X}="
            f"{struct.unpack_from('<I', dat, hair_off)[0]} mBeard="
            f"{struct.unpack_from('<I', dat, hair_off + 4)[0]} mMakeup="
            f"{struct.unpack_from('<I', dat, hair_off + 8)[0]} "
            f"(edt hair={struct.unpack_from('<H', edt, 0x15)[0]} "
            f"beard={edt[0x19]} makeup={edt[0x21]} — not written)"
        )
        print("NOTE: Female NPC -> start from a Female template slot (editdata5).")


if __name__ == "__main__":
    main()
