"""Simple Tk UI for edt2dat — no console required."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .catalog import NpcEntry, with_arc_on_disk
from .extract import default_arctool
from .pipeline import npc_to_editdata

# Same folder as Launch edt2dat.bat
TOOL_DIR = Path(__file__).resolve().parent
EXPORTED_DIR = TOOL_DIR / "exported"


def _default_appdata_edit() -> Path:
    """Current Windows user — %LOCALAPPDATA%\\CAPCOM\\…\\edit"""
    local = os.environ.get("LOCALAPPDATA", "")
    return Path(local) / "CAPCOM" / "Dragon's Dogma Online" / "edit"


def _env_path(*keys: str) -> Path | None:
    for k in keys:
        v = os.environ.get(k)
        if v:
            return Path(v)
    return None


def _default_game_folder() -> str:
    """
    Suggested path using only env vars every Windows install has.
    Prefill only if that folder actually exists; otherwise leave empty
    (user Browses).
    """
    # e.g. C:\Program Files (x86)\… or C:\Program Files\…
    roots = []
    for key in ("ProgramFiles(x86)", "ProgramFiles", "PROGRAMFILES(X86)", "PROGRAMFILES"):
        p = _env_path(key)
        if p:
            roots.append(p)

    cands: list[Path] = []
    for root in roots:
        cands.append(
            root / "Steam" / "steamapps" / "common" / "Dragon's Dogma Online"
        )
    # Also: %USERPROFILE%\Games\… (generic place users sometimes use)
    home = _env_path("USERPROFILE")
    if home:
        cands.append(home / "Games" / "Dragon's Dogma Online")
        cands.append(home / "Dragon's Dogma Online")

    for c in cands:
        if (c / "nativePC" / "rom" / "npc").is_dir():
            return str(c)
    # Display a portable hint even if missing — user will Browse if wrong
    pf = _env_path("ProgramFiles(x86)") or _env_path("ProgramFiles")
    if pf:
        return str(pf / "Steam" / "steamapps" / "common" / "Dragon's Dogma Online")
    return ""


def _ensure_exported() -> Path:
    EXPORTED_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORTED_DIR


def _default_out_path(npc_name: str) -> Path:
    return _ensure_exported() / f"{npc_name}_from_edt.dat"


class Edt2DatApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("DDON edt2dat — NPC → character editdata")
        self.minsize(720, 620)
        self.geometry("760x640")

        self._entries: tuple[NpcEntry, ...] = ()
        self._filtered: list[NpcEntry] = []
        self._busy = False

        self.game_var = tk.StringVar(value=_default_game_folder())
        self.arctool_var = tk.StringVar(value=str(default_arctool()))
        self.query_var = tk.StringVar()
        self.out_var = tk.StringVar(value=str(_ensure_exported() / "npc_from_edt.dat"))
        self.slot_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(
            value="Confirm game folder + ARCtool, then Refresh NPC list."
        )

        self._build()
        self.query_var.trace_add("write", lambda *_: self._apply_filter())

        if self.game_var.get() and Path(self.game_var.get(), "nativePC", "rom", "npc").is_dir():
            self.after(100, self.refresh_list)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # Pack bottom chrome first so Convert is never clipped
        btn_fr = ttk.Frame(frm)
        btn_fr.pack(side=tk.BOTTOM, fill=tk.X, **pad)
        self.convert_btn = ttk.Button(btn_fr, text="Convert", command=self.convert)
        self.convert_btn.pack(side=tk.LEFT)
        ttk.Label(btn_fr, textvariable=self.status_var).pack(side=tk.LEFT, padx=12)

        out_fr = ttk.LabelFrame(frm, text="Output", padding=8)
        out_fr.pack(side=tk.BOTTOM, fill=tk.X, **pad)
        self._row_browse(out_fr, 0, "Save .dat as", self.out_var, self._browse_out)
        ttk.Label(out_fr, text="Also install to AppData slot (optional 0–20)").grid(
            row=1, column=0, sticky=tk.W, pady=(6, 0)
        )
        ttk.Entry(out_fr, textvariable=self.slot_var, width=8).grid(
            row=1, column=1, sticky=tk.W, pady=(6, 0), padx=(8, 0)
        )

        path_fr = ttk.LabelFrame(frm, text="Paths", padding=8)
        path_fr.pack(side=tk.TOP, fill=tk.X, **pad)
        self._row_browse(path_fr, 0, "Game folder", self.game_var, self._browse_game)
        self._row_browse(path_fr, 1, "ARCtool.exe", self.arctool_var, self._browse_arctool)
        ttk.Button(path_fr, text="Refresh NPC list", command=self.refresh_list).grid(
            row=2, column=1, sticky=tk.W, pady=(8, 0)
        )

        npc_fr = ttk.LabelFrame(frm, text="NPC (Arrowgene NpcId name)", padding=8)
        npc_fr.pack(side=tk.TOP, fill=tk.BOTH, expand=True, **pad)

        ttk.Label(npc_fr, text="Search").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(npc_fr, textvariable=self.query_var).grid(
            row=0, column=1, sticky=tk.EW, padx=(8, 0)
        )
        npc_fr.columnconfigure(1, weight=1)

        self.listbox = tk.Listbox(npc_fr, height=12, exportselection=False)
        scroll = ttk.Scrollbar(npc_fr, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.grid(row=1, column=0, columnspan=2, sticky=tk.NSEW, pady=(6, 0))
        scroll.grid(row=1, column=2, sticky=tk.NS, pady=(6, 0))
        npc_fr.rowconfigure(1, weight=1)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

    def _row_browse(
        self,
        parent: ttk.LabelFrame,
        row: int,
        label: str,
        var: tk.StringVar,
        cmd,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky=tk.EW, padx=8)
        ttk.Button(parent, text="Browse…", command=cmd).grid(row=row, column=2)
        parent.columnconfigure(1, weight=1)

    def _browse_game(self) -> None:
        d = filedialog.askdirectory(title="Select Dragon's Dogma Online folder")
        if d:
            self.game_var.set(d)
            self.refresh_list()

    def _browse_arctool(self) -> None:
        p = filedialog.askopenfilename(
            title="Select ARCtool.exe",
            initialdir=str(TOOL_DIR),
            filetypes=[("ARCtool", "ARCtool.exe"), ("Executable", "*.exe"), ("All", "*.*")],
        )
        if p:
            self.arctool_var.set(p)

    def _browse_out(self) -> None:
        _ensure_exported()
        cur = (
            Path(self.out_var.get())
            if self.out_var.get().strip()
            else _default_out_path("npc")
        )
        p = filedialog.asksaveasfilename(
            title="Save editdata as",
            defaultextension=".dat",
            filetypes=[("editdata", "*.dat"), ("All", "*.*")],
            initialdir=str(cur.parent if cur.parent.is_dir() else EXPORTED_DIR),
            initialfile=cur.name or "npc_from_edt.dat",
        )
        if p:
            self.out_var.set(p)

    def refresh_list(self) -> None:
        game = Path(self.game_var.get().strip())
        if not game.is_dir():
            messagebox.showerror("Game folder", f"Not a folder:\n{game}")
            return
        npc_dir = game / "nativePC" / "rom" / "npc"
        if not npc_dir.is_dir():
            messagebox.showerror(
                "Game folder",
                f"Missing nativePC\\rom\\npc under:\n{game}\n\n"
                "Select the Dragon's Dogma Online root (Browse).",
            )
            return
        self._entries = with_arc_on_disk(game)
        self.status_var.set(f"{len(self._entries)} NPCs with arcs on disk.")
        self._apply_filter()

    def _apply_filter(self) -> None:
        q = self.query_var.get().strip().lower()
        if not q:
            self._filtered = list(self._entries)
        else:
            self._filtered = [
                e
                for e in self._entries
                if q in e.name.lower() or q in str(e.id) or q in e.arc_name.lower()
            ]
        self.listbox.delete(0, tk.END)
        for e in self._filtered:
            self.listbox.insert(tk.END, f"{e.name}    (id={e.id}, {e.arc_name})")

    def _selected(self) -> NpcEntry | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self._filtered[sel[0]]

    def _on_select(self, _evt=None) -> None:
        e = self._selected()
        if not e:
            return
        desired = _default_out_path(e.name)
        cur = self.out_var.get().strip()
        if not cur:
            self.out_var.set(str(desired))
            return
        cur_p = Path(cur)
        if cur_p.parent.resolve() == EXPORTED_DIR.resolve() or cur_p.name.endswith(
            "_from_edt.dat"
        ):
            self.out_var.set(str(desired))

    def convert(self) -> None:
        if self._busy:
            return
        entry = self._selected()
        if entry is None:
            messagebox.showwarning("NPC", "Select an NPC from the list.")
            return
        game = Path(self.game_var.get().strip())
        arctool = Path(self.arctool_var.get().strip())
        out = Path(self.out_var.get().strip())
        if not arctool.is_file():
            messagebox.showerror(
                "ARCtool",
                f"ARCtool.exe not found:\n{arctool}\n\n"
                f"Place ARCtool.exe in:\n{TOOL_DIR}\n"
                "or Browse to it.",
            )
            return
        if not out.name:
            messagebox.showerror("Output", "Choose where to save the .dat file.")
            return

        slot_txt = self.slot_var.get().strip()
        slot: int | None
        if slot_txt == "":
            slot = None
        else:
            try:
                slot = int(slot_txt)
            except ValueError:
                messagebox.showerror("Slot", "Slot must be a number (or empty).")
                return

        if out.is_file():
            if not messagebox.askyesno(
                "Overwrite file?",
                f"This file already exists and will be replaced:\n\n{out}",
            ):
                return

        slot_dest: Path | None = None
        if slot is not None:
            slot_dest = _default_appdata_edit() / f"editdata{slot}.dat"
            if slot_dest.is_file():
                if not messagebox.askyesno(
                    "Overwrite AppData slot?",
                    f"editdata{slot}.dat already exists for this Windows user "
                    f"and will be replaced:\n\n{slot_dest}",
                ):
                    return

        self._busy = True
        self.convert_btn.configure(state=tk.DISABLED)
        self.status_var.set(f"Converting {entry.name}…")

        def work() -> None:
            try:
                result = npc_to_editdata(
                    game,
                    entry.name,
                    arctool=arctool,
                    verbose=False,
                )
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(result.dat)
                slot_msg = ""
                if slot_dest is not None:
                    slot_dest.parent.mkdir(parents=True, exist_ok=True)
                    slot_dest.write_bytes(result.dat)
                    slot_msg = f"\nInstalled slot: {slot_dest}"
                self.after(
                    0,
                    lambda: self._done_ok(
                        f"{entry.name} → {result.gender}\nWrote: {out}{slot_msg}"
                    ),
                )
            except Exception as e:
                self.after(0, lambda: self._done_err(str(e)))

        threading.Thread(target=work, daemon=True).start()

    def _done_ok(self, msg: str) -> None:
        self._busy = False
        self.convert_btn.configure(state=tk.NORMAL)
        self.status_var.set("Done.")
        messagebox.showinfo("Convert", msg)

    def _done_err(self, msg: str) -> None:
        self._busy = False
        self.convert_btn.configure(state=tk.NORMAL)
        self.status_var.set("Error.")
        messagebox.showerror("Convert failed", msg)


def run_gui() -> int:
    app = Edt2DatApp()
    app.mainloop()
    return 0
