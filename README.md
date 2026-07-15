# edt2dat — NPC look → character editor `.dat`

Pick an Arrowgene **`NpcId` enum name**, point at your DDON game folder, get an `editdata`-compatible `.dat`. No manual `.edt` unpack.

Keep the release folder named **`edt2dat`** (required for `python -m edt2dat`).

---

## Requirements

- Windows + **Python 3.10+** on `PATH`
- DDON client with `nativePC\rom\npc\nXXXX.arc`
- **`ARCtool.exe`** in this folder (same place as `Launch edt2dat.bat`) — the `.exe` only, not a `.bat`
- Bundled files already present: `data/templates/`, `data/npc_ids.json`

---

## Windowed UI (recommended)

1. Put `ARCtool.exe` next to `Launch edt2dat.bat` if it is not already there  
2. Double-click **`Launch edt2dat.bat`**  
   (or from the **parent** of this folder: `python -m edt2dat`)

### Steps in the window

1. **Game folder** — DDON root that contains `nativePC`  
2. **ARCtool.exe** — Browse if needed  
3. **Refresh NPC list** — search / pick enum name (e.g. `AdairDonnchadh1`, `Nedo0`)  
4. **Save .dat as…**  
5. Optional **AppData slot** `0–20`  
6. **Convert**

### Default paths (portable)

| Field | Default |
|--------|---------|
| Game folder | `%ProgramFiles(x86)%\Steam\steamapps\common\Dragon's Dogma Online` (from Windows env). Also tries `%USERPROFILE%\Games\Dragon's Dogma Online` and `%USERPROFILE%\Dragon's Dogma Online`. Browse if wrong. |
| ARCtool.exe | `ARCtool.exe` in **this tool folder** |
| Save .dat | `exported\<NpcName>_from_edt.dat` (created next to the launch bat) |
| AppData slot | **Current Windows user:** `%LOCALAPPDATA%\CAPCOM\Dragon's Dogma Online\edit\editdataN.dat` |

### Overwrite

- Output `.dat` already exists → Yes/No before replace  
- AppData `editdataN.dat` already exists → Yes/No before replace  

---

## CLI (optional)

From the **parent directory** of `edt2dat`:

```bat
python -m edt2dat list --game "%ProgramFiles(x86)%\Steam\steamapps\common\Dragon's Dogma Online" -q Nedo

python -m edt2dat convert --game "…" --npc Nedo0 -o edt2dat\exported\Nedo0_from_edt.dat

python -m edt2dat convert --game "…" --npc Mysial0 --slot 9 -v
```

`--npc` accepts Arrowgene enum name or numeric id.  
`--arctool` can override the path to `ARCtool.exe`.

---

## Behavior (product rules)

| Topic | Rule |
|-------|------|
| Names | Arrowgene enum as-is (`AdairDonnchadh1`, `AdairDonnchadh2`, …) |
| Multi-`.edt` in one arc | **First** (prefer `*_00`) |
| No arc / no `.edt` | Omitted from refreshed list; convert errors clearly |
| Sex | From `.edt` `@0x14` → male/female bundled template + `.dat` sex fields |
| Hair / beard / makeup **styles** | Left on template (colors still map) |
| Stance | Left on template (no live NPC `.edt` source yet) |
| ARCtool | Direct `.exe` with `-ddo -texRE6 -alwayscomp -pc -txt -v 7` |

---

## Layout (this folder)

```
edt2dat/
  Launch edt2dat.bat
  ARCtool.exe              # place here for end users
  exported/                # default .dat output
  gui.py                   # Tk UI
  cli.py                   # list / convert / gui
  catalog.py
  extract.py
  pipeline.py
  edt_to_editdata.py       # morph inject (translate)
  data/
    npc_ids.json
    templates/
      male.dat
      female.dat
```

---

## Developer notes

### Style

Keep code **declarative + functional**: small helpers, data in JSON / `BODY_H_POS`, compose `extract → translate → write`. Tk stays a thin UI over `pipeline.npc_to_editdata`.

### Pipeline

```
NpcId name → {game}/nativePC/rom/npc/n{id:04d}.arc
  → ARCtool extract → first *.3E894FE7 / .edt
  → gender @0x14
  → data/templates/{male|female}.dat
  → edt_to_editdata.translate(...)
  → exported/*.dat and/or AppData editdataN.dat
```

### Regenerate `data/npc_ids.json`

Source enum: Arrowgene `NpcId.cs`  
(`Arrowgene.Ddon.Shared/Model/NpcId.cs` on the Arrowgene GitHub `develop` branch).

Parse `Name = 123,` into:

```json
{ "source": "NpcId.cs", "npcs": [ { "name": "Nedo0", "id": 29 }, … ] }
```

Keep enum names exact (including `0` / `1` suffixes).

### Templates

- **Male** template: safe character-editor male slot dump (avoid layouts that embed a fragile mid-block “Male” string).  
- **Female** template: safe female slot dump.  
- Smoke-test after changes: `Nedo0` (male) and `Mysial0` (female).

### Morph maps

Edit **`edt_to_editdata.py`** inside this package (`BODY_H_POS`, `FACE_H_NEG`, `translate`). Research notes for confirmed `.edt` offsets live with your internal experiment docs if you maintain them separately — they are not required to run the tool.

### Sharing a zip

Ship the whole **`edt2dat`** folder (keep that name), including:

- `ARCtool.exe`
- `data/`
- `exported/` (can be empty)
- `Launch edt2dat.bat`

Users need Python installed unless you later freeze with PyInstaller.

### Smoke checks

```bat
cd ..
python -m edt2dat list --game "%ProgramFiles(x86)%\Steam\steamapps\common\Dragon's Dogma Online" -q Mysial
python -m edt2dat convert --game "…" --npc Mysial0 -o edt2dat\exported\_smoke.dat -v
```

Expect sex **Female**, file size ~23840 bytes, and a Chest line in the verbose morph log.
