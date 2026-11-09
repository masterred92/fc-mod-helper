"""FC Mod Helper: the one-window app. All decisions live in app_logic.py; this file only draws."""

from __future__ import annotations

import os
import sys
import webbrowser
from importlib import resources
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

from fcmh import app_logic as logic
from fcmh import detect
from fcmh import version as version_mod
from fcmh.ledger import Ledger, default_ledger_path, normalize_tu

try:  # optional drag and drop
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
except Exception:  # noqa: BLE001
    TkinterDnD = None
    DND_FILES = None

BG = "#f4f6fb"
INK = "#1d2433"
MUTED = "#5b6475"
TILE_COLORS = {
    "play": "#1f9d55", "add": "#3554d1", "update": "#e07b00", "backup": "#5b4bc4",
    "restore": "#00838f", "academy": "#c2185b", "scout": "#6a1b9a", "online": "#546e7a",
}
BANNER = {logic.GREEN: ("#e3f5ea", "#1f9d55"), logic.YELLOW: ("#fff5d6", "#d49b00"),
          logic.RED: ("#fde4e4", "#c62828")}


def set_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def font_family() -> str:
    return "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


def lighten(color: str, amount: float = 0.15) -> str:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    r, g, b = (int(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def short(path, limit: int = 58) -> str:
    text = str(path) if path else ""
    return text if len(text) <= limit else "..." + text[-(limit - 3):]


class Fonts:
    def __init__(self) -> None:
        fam = font_family()
        self.title = (fam, 24, "bold")
        self.h2 = (fam, 17, "bold")
        self.tile = (fam, 16, "bold")
        self.body = (fam, 13)
        self.small = (fam, 11)
        self.button = (fam, 13, "bold")


def status_dot(parent, color: str, size: int = 30, mark: str = "tick", bg: str = BG) -> tk.Canvas:
    canvas = tk.Canvas(parent, width=size, height=size, bg=bg, highlightthickness=0)
    canvas.create_oval(2, 2, size - 2, size - 2, fill=color, outline=color)
    s = size / 30
    if mark == "tick":
        canvas.create_line(8 * s, 15 * s, 13 * s, 21 * s, 23 * s, 9 * s, fill="white", width=3.5 * s,
                           capstyle="round", joinstyle="round")
    else:
        canvas.create_line(15 * s, 7 * s, 15 * s, 17 * s, fill="white", width=3.5 * s, capstyle="round")
        canvas.create_oval(13 * s, 20 * s, 17 * s, 24 * s, fill="white", outline="white")
    return canvas


class BigButton(tk.Frame):
    """A large coloured tile with an icon, a title and one line of plain words."""

    def __init__(self, parent, color: str, icon: tk.PhotoImage | None, title: str, subtitle: str,
                 command, fonts: Fonts, wide: bool = False) -> None:
        super().__init__(parent, bg=color, cursor="hand2", padx=18, pady=14)
        self.color, self.command = color, command
        self.widgets = [self]
        if icon is not None:
            label = tk.Label(self, image=icon, bg=color)
            label.grid(row=0, column=0, rowspan=2, padx=(0, 14))
            self.widgets.append(label)
        t = tk.Label(self, text=title, font=fonts.h2 if not wide else fonts.title, fg="white", bg=color, anchor="w",
                     justify="left")
        t.grid(row=0, column=1, sticky="w")
        s = tk.Label(self, text=subtitle, font=fonts.small, fg="white", bg=color, anchor="w", justify="left")
        s.grid(row=1, column=1, sticky="w")
        self.widgets += [t, s]
        self.columnconfigure(1, weight=1)
        self.text_labels = [t, s]
        self.bind("<Configure>", self._rewrap)
        for widget in self.widgets:
            widget.bind("<Button-1>", lambda _e: self.command())
            widget.bind("<Enter>", lambda _e: self._paint(lighten(self.color)))
            widget.bind("<Leave>", lambda _e: self._paint(self.color))

    def _rewrap(self, event) -> None:
        room = max(event.width - 130, 120)
        for label in self.text_labels:
            label.configure(wraplength=room)

    def _paint(self, color: str) -> None:
        for widget in self.widgets:
            widget.configure(bg=color)


class Dialog(tk.Toplevel):
    """A big, simple modal dialog with plain buttons."""

    def __init__(self, app: "App", title: str, message: str, buttons: list[tuple[str, object]],
                 extra=None, width: int = 560) -> None:
        super().__init__(app.root)
        self.app, self.result = app, None
        self.title(title)
        self.configure(bg="white", padx=26, pady=22)
        self.resizable(False, False)
        self.transient(app.root)
        tk.Label(self, text=title, font=app.fonts.h2, bg="white", fg=INK, anchor="w").pack(fill="x")
        tk.Label(self, text=message, font=app.fonts.body, bg="white", fg=INK, justify="left",
                 wraplength=width, anchor="w").pack(fill="x", pady=(10, 14))
        if extra:
            extra(self)
        row = tk.Frame(self, bg="white")
        row.pack(fill="x", pady=(8, 0))
        for index, (label, value) in enumerate(buttons):
            primary = index == 0
            button = tk.Button(row, text=label, font=app.fonts.button, padx=20, pady=8, relief="flat",
                               bg="#1f9d55" if primary else "#e6e9f0", fg="white" if primary else INK,
                               activebackground=lighten("#1f9d55") if primary else "#d6dbe6",
                               cursor="hand2", command=lambda v=value: self.close(v))
            button.pack(side="right", padx=(10, 0))
        self.protocol("WM_DELETE_WINDOW", lambda: self.close(None))
        self.bind("<Escape>", lambda _e: self.close(None))
        self.update_idletasks()
        x = app.root.winfo_rootx() + max((app.root.winfo_width() - self.winfo_width()) // 2, 0)
        y = app.root.winfo_rooty() + max((app.root.winfo_height() - self.winfo_height()) // 3, 0)
        self.geometry(f"+{x}+{y}")
        app.open_dialog = self

    def close(self, value) -> None:
        self.result = value
        self.app.open_dialog = None
        self.destroy()

    def run(self):
        if self.app.no_wait:
            return self.app.auto_answer(self)
        self.grab_set()
        self.wait_window()
        return self.result


class App:
    def __init__(self, root: tk.Tk, ledger_path: Path | None = None, probe: detect.Probe | None = None,
                 detector=None, no_wait: bool = False) -> None:
        self.root = root
        self.ledger_path = Path(ledger_path or default_ledger_path())
        self.probe = probe
        self.detector = detector or version_mod.detect
        self.no_wait = no_wait  # screenshots/tests: dialogs don't block
        self.auto_answers: list = []
        self.keep_dialogs = False
        self.display_path = str  # screenshots swap this to show Windows-style demo paths
        self.open_dialog: Dialog | None = None
        self.fonts = Fonts()
        self.icons = {}
        self.asked_files: set[str] = set()
        self.ledger: Ledger | None = None
        self.content: tk.Frame | None = None
        self.screen = "start"
        self.scout_seen: str | None = None
        self.scout_sort = "best"
        self.scout_show_signed = False
        self.scout_result: logic.ScoutResult | None = None
        root.title("FC Mod Helper")
        root.configure(bg=BG)
        root.minsize(860, 700)
        self._load_icons()
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

    # ---- helpers -------------------------------------------------------
    def _load_icons(self) -> None:
        base = resources.files("fcmh.assets")
        for name in ("play", "add", "update", "backup", "restore", "academy", "scout", "online", "more", "app"):
            try:
                with resources.as_file(base.joinpath(f"{name}.png")) as path:
                    image = tk.PhotoImage(file=str(path))
                self.icons[name] = image.subsample(2) if name != "play" else image.subsample(2)
            except Exception:  # noqa: BLE001
                self.icons[name] = None
        if self.icons.get("app") is not None:
            try:
                self.root.iconphoto(True, self.icons["app"])
            except tk.TclError:
                pass

    def auto_answer(self, dialog: Dialog):
        value = self.auto_answers.pop(0) if self.auto_answers else None
        if not self.keep_dialogs:
            dialog.close(value)
        return value

    def ask_yes_no(self, title: str, question: str) -> bool:
        return Dialog(self, title, question, [("Yes", True), ("No", False)]).run() is True

    def tell(self, title: str, message: str) -> None:
        Dialog(self, title, message, [("OK", True)]).run()

    def ask_text(self, title: str, message: str, initial: str = "") -> str | None:
        var = tk.StringVar(value=initial)

        def extra(dlg):
            entry = tk.Entry(dlg, textvariable=var, font=self.fonts.h2, width=16, relief="solid", bd=1)
            entry.pack(anchor="w", pady=(0, 6))
            entry.focus_set()

        answer = Dialog(self, title, message, [("OK", True), ("Cancel", False)], extra=extra).run()
        return var.get().strip() if answer else None

    def choose(self, title: str, message: str, options: list[str], ok_label: str = "Keep this one") -> str | None:
        var = tk.StringVar(value=options[0] if options else "")

        def extra(dlg):
            for option in options:
                tk.Radiobutton(dlg, text=option, variable=var, value=option, font=self.fonts.body, bg="white",
                               anchor="w", activebackground="white", selectcolor="white").pack(fill="x", pady=2)

        answer = Dialog(self, title, message, [(ok_label, True), ("Cancel", False)], extra=extra).run()
        return var.get() if answer else None

    def pick_from_list(self, title: str, message: str, items: list[str], ok_label: str) -> int | None:
        box_holder = {}

        def extra(dlg):
            box = tk.Listbox(dlg, font=self.fonts.body, height=min(max(len(items), 3), 8), width=46,
                             activestyle="none", selectbackground="#3554d1", relief="solid", bd=1)
            for item in items:
                box.insert("end", item)
            if items:
                box.selection_set(0)
            box.pack(fill="x")
            box_holder["box"] = box

        selection = {}

        def remember(value):
            sel = box_holder["box"].curselection()
            selection["index"] = sel[0] if sel else None
            return value

        dlg = Dialog(self, title, message, [(ok_label, "ok"), ("Cancel", None)], extra=extra)
        original_close = dlg.close
        dlg.close = lambda v: original_close(remember(v))  # type: ignore[method-assign]
        answer = dlg.run()
        if self.no_wait:
            return 0 if answer == "ok" and items else None
        return selection.get("index") if answer == "ok" else None

    def busy(self, on: bool) -> None:
        self.root.configure(cursor="watch" if on else "")
        self.root.update_idletasks()

    def clear(self) -> tk.Frame:
        self.screen = "other"
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.unbind_all(seq)
        if self.content is not None:
            self.content.destroy()
        self.content = tk.Frame(self.root, bg=BG, padx=28, pady=20)
        self.content.pack(fill="both", expand=True)
        return self.content

    # ---- start ---------------------------------------------------------
    def start(self) -> None:
        self.ledger = logic.load_ledger(self.ledger_path)
        if self.ledger is None:
            self.show_warning()
        else:
            self.show_main()
        self.root.after(4000, self.poll_mods_folder)

    # ---- first run -----------------------------------------------------
    def show_warning(self) -> None:
        frame = self.clear()
        tk.Label(frame, text="Welcome to FC Mod Helper", font=self.fonts.title, bg=BG, fg=INK).pack(anchor="w")
        tk.Label(frame, text="Before we start, please read this.", font=self.fonts.body, bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 16))
        card = tk.Frame(frame, bg="#fff5d6", padx=22, pady=18, highlightbackground="#d49b00", highlightthickness=2)
        card.pack(fill="x")
        row = tk.Frame(card, bg="#fff5d6")
        row.pack(fill="x")
        status_dot(row, "#d49b00", 40, "warn", bg="#fff5d6").pack(side="left", padx=(0, 14), anchor="n")
        tk.Label(row, text=logic.RISK_WARNING, font=self.fonts.body, bg="#fff5d6", fg=INK, justify="left",
                 wraplength=700, anchor="w").pack(side="left", fill="x")
        tk.Button(frame, text="I understand. Mods only offline. Next", font=self.fonts.h2, bg="#1f9d55", fg="white",
                  activebackground=lighten("#1f9d55"), activeforeground="white", relief="flat", padx=28, pady=14,
                  cursor="hand2", command=self.show_setup).pack(anchor="e", pady=24)

    def show_setup(self) -> None:
        frame = self.clear()
        tk.Label(frame, text="Finding everything for you...", font=self.fonts.title, bg=BG, fg=INK).pack(anchor="w")
        self.root.update()
        self.busy(True)
        found, info, items = logic.run_detection(self.probe, self.detector)
        self.busy(False)
        self.setup_state = {
            "game": found.games[0].game if found.games else "fc26",
            "install": found.games[0].path if found.games else None,
            "tu": (info or {}).get("tu"), "exe_version": (info or {}).get("exe_version"),
            "mod_manager": found.mod_manager_exe, "saves": found.settings_dir, "temp": found.temp_dir,
            "live_editor": found.live_editor_dir, "found": found,
        }
        self.render_setup(items)

    def _setup_items(self) -> list[logic.SetupItem]:
        st = self.setup_state
        found = detect.Detection(
            games=[detect.GameInstall(st["game"], Path(st["install"]), "you picked it" if not st["found"].games else st["found"].games[0].source)] if st["install"] else [],
            mod_manager_exe=st["mod_manager"], live_editor_dir=st["live_editor"],
            settings_dir=st["saves"], temp_dir=st["temp"])
        return logic.setup_items(found, {"tu": st["tu"], "exe_version": st["exe_version"]})

    def render_setup(self, items: list[logic.SetupItem] | None = None) -> None:
        items = items or self._setup_items()
        frame = self.clear()
        tk.Label(frame, text="Here's what I found", font=self.fonts.title, bg=BG, fg=INK).pack(anchor="w")
        tk.Label(frame, text="Green means done. Yellow means please show me where it is.", font=self.fonts.body,
                 bg=BG, fg=MUTED).pack(anchor="w", pady=(2, 14))
        for item in items:
            card = tk.Frame(frame, bg="white", padx=16, pady=10)
            card.pack(fill="x", pady=4)
            color = "#1f9d55" if item.ok else "#d49b00"
            status_dot(card, color, 34, "tick" if item.ok else "warn", bg="white").pack(side="left", padx=(0, 14))
            text = tk.Frame(card, bg="white")
            text.pack(side="left", fill="x", expand=True)
            tk.Label(text, text=item.label, font=self.fonts.h2, bg="white", fg=INK, anchor="w").pack(fill="x")
            shown = self.display_path(item.value) if item.value else ""
            detail = item.note if item.key == "version" else (short(shown) if item.value else item.note)
            if item.key == "game" and item.ok:
                detail = f"{item.note}: {short(shown, 40)}"
            tk.Label(text, text=detail or "", font=self.fonts.small, bg="white", fg=MUTED, anchor="w").pack(fill="x")
            label = "Change" if item.ok else ("Type it" if item.key == "version" else "Please pick")
            tk.Button(card, text=label, font=self.fonts.button, relief="flat", padx=14, pady=6, cursor="hand2",
                      bg="#e6e9f0" if item.ok else "#d49b00", fg=INK if item.ok else "white",
                      command=lambda k=item.key: self.pick_setup_item(k)).pack(side="right")
        ready = self.setup_state["install"] is not None
        tk.Button(frame, text="All done - let's go!" if ready else "Pick your game first", font=self.fonts.button,
                  bg="#1f9d55" if ready else "#9aa3b5", fg="white", relief="flat", padx=24, pady=10,
                  state="normal" if ready else "disabled", cursor="hand2",
                  command=self.finish_setup).pack(anchor="e", pady=(16, 0))

    def pick_setup_item(self, key: str) -> None:
        st = self.setup_state
        if key == "game":
            folder = filedialog.askdirectory(title="Pick your EA SPORTS FC game folder")
            if folder:
                path = Path(folder)
                game = next((g for g in ("fc27", "fc26") if detect.is_game_dir(g, path)), None)
                if game is None:
                    self.tell("That's not the game folder", "I couldn't see FC26.exe or FC27.exe in that folder. "
                              "Please pick the folder the game is installed in.")
                    return
                st["game"], st["install"] = game, path
                info = self.detector(game, path)
                st["tu"], st["exe_version"] = info.get("tu"), info.get("exe_version")
        elif key == "version":
            typed = self.ask_text("Which game update do you have?",
                                  "You can see it on the game's start screen or in the patch notes, e.g. 1.6.6.",
                                  st["tu"] or "")
            if typed:
                try:
                    st["tu"] = normalize_tu(typed)
                except Exception:  # noqa: BLE001
                    self.tell("Hmm", "That doesn't look like a game update number. Try something like 1.6.6.")
        elif key == "mod_manager":
            exe = filedialog.askopenfilename(title="Pick FIFA Mod Manager.exe",
                                             filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
            if exe:
                st["mod_manager"] = Path(exe)
        elif key in ("saves", "temp", "live_editor"):
            folder = filedialog.askdirectory(title={"saves": "Pick the 'settings' folder with your Career saves",
                                                    "temp": "Pick the game's temp folder",
                                                    "live_editor": "Pick your Live Editor folder"}[key])
            if folder:
                st[key] = Path(folder)
        self.render_setup()

    def finish_setup(self) -> None:
        st = self.setup_state
        self.ledger = logic.save_setup(self.ledger_path, st["game"], Path(st["install"]), tu=st["tu"],
                                       exe_version=st["exe_version"], mod_manager_exe=st["mod_manager"],
                                       settings_dir=st["saves"], temp_dir=st["temp"],
                                       live_editor_dir=st["live_editor"])
        self.show_main()

    # ---- main window ---------------------------------------------------
    def show_main(self) -> None:
        frame = self.clear()
        self.screen = "main"
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x")
        if self.icons.get("app") is not None:
            tk.Label(top, image=self.icons["app"], bg=BG).pack(side="left", padx=(0, 12))
        titles = tk.Frame(top, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="FC Mod Helper", font=self.fonts.title, bg=BG, fg=INK).pack(anchor="w")
        tk.Label(titles, text="Safe, simple mods for offline Career Mode", font=self.fonts.body, bg=BG,
                 fg=MUTED).pack(anchor="w")
        more = tk.Menubutton(top, text="More  \u25be", font=self.fonts.button, bg="#e6e9f0", fg=INK, relief="flat",
                             padx=14, pady=6, cursor="hand2")
        menu = tk.Menu(more, tearoff=False, font=self.fonts.body)
        menu.add_command(label="Run setup again", command=self.show_setup)
        menu.add_command(label="Tell me the game update", command=lambda: self.run_fix("set_update"))
        menu.add_command(label="Find Mod Manager", command=lambda: self.run_fix("pick_mod_manager"))
        menu.add_command(label="Find Live Editor", command=self.pick_live_editor)
        menu.add_command(label="Add a mod page link", command=self.add_link)
        menu.add_separator()
        menu.add_command(label="Open my Mods folder", command=lambda: self.open_folder("mods_dir"))
        menu.add_command(label="Open my backups folder", command=lambda: self.open_folder("backup_dir"))
        menu.add_command(label="Open my Scouting folder", command=lambda: self.open_folder("scouting_dir"))
        more.configure(menu=menu)
        more.pack(side="right")

        self.banner = tk.Frame(frame, padx=16, pady=12)
        self.banner.pack(fill="x", pady=(16, 14))

        grid = tk.Frame(frame, bg=BG)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1, uniform="c")
        grid.columnconfigure(1, weight=1, uniform="c")
        tiles = [
            ("play", "Play safely", "Checks everything, backs up your saves, then opens Mod Manager", self.on_play, True),
            ("add", "Add mods", "Pick mod files (or drop them on this window)", self.on_add, False),
            ("update", "Game updated? Fix my mods", "Cleans up and shows which mods need updating", self.on_update, False),
            ("backup", "Back up now", "Saves a copy of your Career saves", self.on_backup, False),
            ("restore", "Restore", "Go back to an earlier backup", self.on_restore, False),
            ("academy", "My academy", "See how your young players are growing", self.on_academy, False),
            ("scout", "Scout preview", "See your scouted kids' real potential before you sign", self.on_scout, False),
            ("online", "Playing online?", "What to switch off first", self.on_online, "span"),
        ]
        row = col = 0
        for key, title, sub, command, wide in tiles:
            tile = BigButton(grid, TILE_COLORS[key], self.icons.get(key), title, sub, command, self.fonts,
                             wide is True)
            if wide:
                tile.grid(row=row, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
                row += 1
                continue
            tile.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
            col += 1
            if col == 2:
                col, row = 0, row + 1
        for r in range(row + 1):
            grid.rowconfigure(r, weight=1)
        if TkinterDnD is not None and DND_FILES is not None:
            try:
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind("<<Drop>>", self.on_drop)
            except Exception:  # noqa: BLE001
                pass
        self.refresh_status()

    def show_banner(self, status: logic.Status) -> None:
        for child in self.banner.winfo_children():
            child.destroy()
        bg, fg = BANNER[status.level]
        self.banner.configure(bg=bg, highlightbackground=fg, highlightthickness=2)
        status_dot(self.banner, fg, 32, "tick" if status.level == logic.GREEN else "warn", bg=bg).pack(side="left", padx=(0, 12))
        if status.fix:
            tk.Button(self.banner, text=status.fix_label, font=self.fonts.button, bg=fg, fg="white", relief="flat",
                      padx=14, pady=6, cursor="hand2",
                      command=lambda: self.run_fix(status.fix, status)).pack(side="right", padx=(12, 0))
        text = tk.Label(self.banner, text=status.sentence, font=self.fonts.h2 if len(status.sentence) < 70 else self.fonts.body,
                        bg=bg, fg=INK, justify="left", anchor="w")
        text.pack(side="left", fill="x", expand=True)
        self.banner.update_idletasks()
        room = max(self.root.winfo_width() - (420 if status.fix else 160), 300)
        text.configure(wraplength=room)
        self.current_status = status

    def refresh_status(self) -> logic.Status:
        status = logic.status(self.ledger, self.detector)
        self.show_banner(status)
        return status

    # ---- fixes ---------------------------------------------------------
    def run_fix(self, fix: str, status: logic.Status | None = None) -> None:
        if fix == "game_updated":
            self.on_update()
            return
        if fix == "remove_missing":
            gone = logic.remove_missing(self.ledger)
            self.tell("Tidied up", f"Removed from your list: {', '.join(gone) or 'nothing'}.")
        elif fix == "choose_clash" and status is not None:
            self.resolve_clash(status.detail)
        elif fix == "pick_mod_manager":
            exe = filedialog.askopenfilename(title="Pick FIFA Mod Manager.exe",
                                             filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
            if exe:
                self.ledger.paths["fmm_exe"] = exe
                self.ledger.paths["fmm_dir"] = str(Path(exe).parent)
                self.ledger.save()
        elif fix == "set_update":
            typed = self.ask_text("Which game update do you have?", "For example 1.6.6.", self.ledger.current_build)
            if typed:
                try:
                    self.ledger.current_build = normalize_tu(typed) or ""
                    self.ledger.save()
                except Exception:  # noqa: BLE001
                    self.tell("Hmm", "That doesn't look like a game update number. Try something like 1.6.6.")
        self.refresh_status()

    def resolve_clash(self, mods: list[str]) -> None:
        keep = self.choose("Pick one", "These mods change the same thing, so only one can be on. "
                           "Which one do you want to keep?", mods)
        if keep:
            off = logic.keep_only(self.ledger, keep, mods)
            self.tell("Done", f"Kept {keep}. Turned off: {', '.join(off)}.\n\nPlease untick the same mods in Mod Manager.")

    # ---- buttons -------------------------------------------------------
    def on_play(self) -> None:
        self.busy(True)
        try:
            result = logic.play_safely(self.ledger, detector=self.detector)
        finally:
            self.busy(False)
        if result.ok:
            self.show_banner(result.status)
            return
        self.show_banner(result.status)
        buttons = [(result.status.fix_label, "fix"), ("Close", None)] if result.status.fix else [("OK", None)]
        if Dialog(self, "Not quite ready", result.status.sentence, buttons).run() == "fix":
            self.run_fix(result.status.fix, result.status)

    def on_add(self) -> None:
        files = filedialog.askopenfilenames(title="Pick your mod files",
                                            filetypes=[("Mods", "*.fifamod *.fbmod"), ("All files", "*.*")])
        if files:
            self.add_files([Path(f) for f in files])

    def on_drop(self, event) -> None:
        files = [Path(f) for f in self.root.tk.splitlist(event.data)]
        self.add_files(files)

    def add_files(self, files: list[Path]) -> None:
        result = logic.add_mod_files(self.ledger, files)
        self.tell("Mods added" if result.added else "Nothing added", result.sentence)
        for clash in result.clashes:
            self.resolve_clash(clash.mods)
        self.refresh_status()

    def add_link(self) -> None:
        if not self.ledger.mods:
            self.tell("No mods yet", "Add a mod first.")
            return
        name = self.choose("Add a mod page link", "Which mod?", [m.name for m in self.ledger.mods], "Next")
        if name:
            url = self.ask_text("Mod page link", f"Paste the web address of the page for {name}.",
                                self.ledger.find_mod(name).author_url)
            if url is not None:
                logic.set_mod_link(self.ledger, name, url)

    def on_update(self) -> None:
        def ask_update():
            return self.ask_text("Which game update is it now?",
                                 "I couldn't read it from the game. Type the number from the patch notes, e.g. 1.6.7.")
        self.busy(True)
        try:
            result = logic.game_updated(self.ledger, self.ask_yes_no, open_url=webbrowser.open,
                                        ask_update=ask_update, detector=self.detector)
        finally:
            self.busy(False)
        self.tell("Game update", result.sentence)
        self.refresh_status()

    def on_backup(self) -> None:
        self.busy(True)
        try:
            path = logic.backup_now(self.ledger)
        finally:
            self.busy(False)
        self.show_banner(logic.Status(logic.GREEN, f"Backed up just now ({path.name})."))

    def on_restore(self) -> None:
        points = logic.restore_points(self.ledger)
        if not points:
            self.tell("No backups yet", "Press 'Back up now' first.")
            return
        index = self.pick_from_list("Restore a backup", "Pick the backup you want to go back to:",
                                    [p.text for p in points], "Restore this one")
        if index is None:
            return
        self.busy(True)
        try:
            message = logic.restore(self.ledger, points[index].path, self.ask_yes_no)
        finally:
            self.busy(False)
        self.tell("Restore", message)

    def on_academy(self) -> None:
        setup = logic.academy_setup(self.ledger)
        report = logic.academy_report(self.ledger)
        if report.report is not None:
            webbrowser.open(report.report.as_uri())
            self.show_banner(logic.Status(logic.GREEN, report.sentence + " It's open in your browser."))
        else:
            self.tell("My academy", setup.sentence if setup.script_path else report.sentence)

    # ---- Scout preview -------------------------------------------------
    def on_scout(self) -> None:
        if not logic.scout_supported(self.ledger):
            self.tell("Scout preview", "Scout preview works with FC 26 for now. FC 27 is coming soon.")
            return
        self.busy(True)
        try:
            result = logic.scout_preview(self.ledger)
        finally:
            self.busy(False)
        if not result.players:
            self.scout_seen = str(result.csv) if result.csv else None
            self.tell("Scout preview", result.sentence)
            return
        self.show_scout(result)

    def show_scout(self, result: logic.ScoutResult | None = None) -> None:
        result = result or logic.scout_preview(self.ledger)
        self.scout_result = result
        self.scout_seen = f"{result.csv}:{result.csv.stat().st_mtime_ns}" if result.csv and result.csv.exists() else None
        frame = self.clear()
        self.screen = "scout"
        top = tk.Frame(frame, bg=BG)
        top.pack(fill="x")
        tk.Button(top, text="\u25c0  Back", font=self.fonts.button, bg="#e6e9f0", fg=INK, relief="flat", padx=14,
                  pady=6, cursor="hand2", command=self.show_main).pack(side="left", padx=(0, 16))
        titles = tk.Frame(top, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="Scout preview", font=self.fonts.title, bg=BG, fg=INK).pack(anchor="w")
        tk.Label(titles, text="FC 26  \u00b7  FC 27 coming soon", font=self.fonts.small, bg=BG, fg=MUTED).pack(anchor="w")
        tk.Button(top, text="Make a web page", font=self.fonts.button, bg=TILE_COLORS["scout"], fg="white",
                  activebackground=lighten(TILE_COLORS["scout"]), relief="flat", padx=14, pady=6, cursor="hand2",
                  command=self.export_scout).pack(side="right")

        info = tk.Frame(frame, bg="#efe6fb", padx=14, pady=10)
        info.pack(fill="x", pady=(14, 8))
        source = self.display_path(result.csv.name) if result.csv else ""
        tk.Label(info, text=result.sentence, font=self.fonts.h2, bg="#efe6fb", fg=INK, anchor="w").pack(anchor="w")
        tk.Label(info, text=f"From {source}. New reports show up here by themselves. Gold = PlayStyles+.",
                 font=self.fonts.small, bg="#efe6fb", fg=MUTED, anchor="w").pack(anchor="w")

        bar = tk.Frame(frame, bg=BG)
        bar.pack(fill="x", pady=(0, 8))
        tk.Label(bar, text="Sort:", font=self.fonts.body, bg=BG, fg=INK).pack(side="left", padx=(0, 6))
        for key, label in (("best", "Best first"), ("potential", "Potential"), ("age", "Youngest"), ("ovr", "Rating now")):
            on = key == self.scout_sort
            tk.Button(bar, text=label, font=self.fonts.small, relief="flat", padx=10, pady=4, cursor="hand2",
                      bg=TILE_COLORS["scout"] if on else "#e6e9f0", fg="white" if on else INK,
                      command=lambda k=key: self._scout_sort(k)).pack(side="left", padx=2)
        var = tk.BooleanVar(value=self.scout_show_signed)
        tk.Checkbutton(bar, text="Show players I already signed", variable=var, font=self.fonts.small, bg=BG,
                       activebackground=BG, command=lambda: self._scout_signed(var.get())).pack(side="right")

        holder = tk.Frame(frame, bg=BG)
        holder.pack(fill="both", expand=True)
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        def wheel(event):
            step = -1 if (getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4) else 1
            canvas.yview_scroll(step * 2, "units")
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind_all(seq, wheel)

        inner.columnconfigure(0, weight=1, uniform="s")
        inner.columnconfigure(1, weight=1, uniform="s")
        players = self._scout_players()
        if not players:
            tk.Label(inner, text="Nobody to show. Tick 'Show players I already signed' to see everyone.",
                     font=self.fonts.body, bg=BG, fg=MUTED).grid(row=0, column=0, columnspan=2, sticky="w", pady=20)
        for index, player in enumerate(players):
            self._scout_card(inner, player).grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)

    def _scout_players(self) -> list:
        players = list(self.scout_result.players if self.scout_result else [])
        if not self.scout_show_signed:
            players = [p for p in players if not p.signed]
        keys = {
            "best": lambda p: (-p.score, -(p.potential or 0)),
            "potential": lambda p: (-(p.potential or 0), p.age or 99),
            "age": lambda p: (p.age or 99, -(p.potential or 0)),
            "ovr": lambda p: (-(p.ovr or 0), -(p.potential or 0)),
        }
        return sorted(players, key=keys[self.scout_sort])

    def _scout_sort(self, key: str) -> None:
        self.scout_sort = key
        self.show_scout(self.scout_result)

    def _scout_signed(self, value: bool) -> None:
        self.scout_show_signed = value
        self.show_scout(self.scout_result)

    def _scout_card(self, parent, p) -> tk.Frame:
        edge = "#1f9d55" if p.sign_him else "#dfe3ec"
        bg = "#f3fbf6" if p.sign_him else "white"
        card = tk.Frame(parent, bg=bg, padx=14, pady=10, highlightbackground=edge, highlightthickness=2 if p.sign_him else 1)
        head = tk.Frame(card, bg=bg)
        head.pack(fill="x")
        pot = tk.Frame(head, bg=bg)
        pot.pack(side="right", anchor="n")
        tk.Label(pot, text=str(p.potential if p.potential is not None else "?"), font=(font_family(), 26, "bold"),
                 bg=bg, fg="#3554d1").pack(anchor="e")
        tk.Label(pot, text="potential", font=self.fonts.small, bg=bg, fg=MUTED).pack(anchor="e")
        left = tk.Frame(head, bg=bg)
        left.pack(side="left", fill="x", expand=True)
        name_row = tk.Frame(left, bg=bg)
        name_row.pack(anchor="w")
        tk.Label(name_row, text=p.name, font=self.fonts.h2, bg=bg, fg=INK).pack(side="left")
        if p.sign_him:
            tk.Label(name_row, text=" SIGN HIM ", font=self.fonts.button, bg="#1f9d55", fg="white").pack(side="left", padx=8)
        elif p.signed:
            tk.Label(name_row, text=" signed ", font=self.fonts.small, bg="#cfd5e1", fg=INK).pack(side="left", padx=8)
        tk.Label(left, text=p.stars_text, font=(font_family(), 18), bg=bg, fg="#e0a800").pack(anchor="w")
        facts = f"Age {p.age if p.age is not None else '?'}  \u00b7  {p.positions or '?'}  \u00b7  {p.nationality or '?'}  \u00b7  Now {p.ovr if p.ovr is not None else '?'}"
        wrap = 360
        wrapped: list = []
        self._wrap_label(card, wrapped, text=facts, font=self.fonts.body, bg=bg, fg=INK, wraplength=wrap, justify="left",
                 anchor="w").pack(anchor="w", fill="x")
        if p.playstyles_plus:
            self._wrap_label(card, wrapped, text="PlayStyles+: " + ", ".join(x + "+" for x in p.playstyles_plus), font=self.fonts.button,
                     bg="#ffe08a", fg="#6b4b00", wraplength=wrap, justify="left", padx=6, pady=2).pack(anchor="w", pady=(6, 0))
        if p.playstyles:
            self._wrap_label(card, wrapped, text="PlayStyles: " + ", ".join(p.playstyles), font=self.fonts.small, bg=bg, fg=INK,
                     wraplength=wrap, justify="left").pack(anchor="w", pady=(4, 0))
        if p.traits:
            self._wrap_label(card, wrapped, text="Hidden traits: " + ", ".join(p.traits), font=self.fonts.small, bg=bg, fg="#5b4bc4",
                     wraplength=wrap, justify="left").pack(anchor="w", pady=(2, 0))
        self._wrap_label(card, wrapped, text=p.reason, font=self.fonts.button, bg=bg, fg="#1f7a4d" if p.sign_him else INK,
                 anchor="w").pack(anchor="w", pady=(6, 0))
        extra = []
        if p.range_guess:
            extra.append(f"Game may show {p.range_guess[0]}-{p.range_guess[1]} (guess)")
        if p.scout_report:
            extra.append(f"Found by {p.scout_report}")
        if extra:
            self._wrap_label(card, wrapped, text="  \u00b7  ".join(extra), font=self.fonts.small, bg=bg, fg=MUTED, wraplength=wrap,
                     justify="left").pack(anchor="w")
        card.bind("<Configure>", lambda e: [w.configure(wraplength=max(e.width - 34, 150)) for w in wrapped])
        return card

    @staticmethod
    def _wrap_label(card, wrapped: list, **options) -> tk.Label:
        options.setdefault("anchor", "w")
        label = tk.Label(card, **options)
        wrapped.append(label)
        return label

    def export_scout(self) -> None:
        if not self.scout_result or not self.scout_result.players:
            return
        path = logic.scout_export_html(self.ledger, self.scout_result)
        if not self.no_wait:
            webbrowser.open(path.as_uri())
        self.last_export = path

    def poll_scouting(self) -> None:
        """Shows a new scout report as soon as the game script writes it."""
        if self.ledger is None or not logic.scout_supported(self.ledger):
            return
        newest = logic.newest_scout_csv(self.ledger)
        if newest is None:
            return
        key = f"{newest}:{newest.stat().st_mtime_ns}"
        if key == self.scout_seen:
            return
        if self.screen == "scout":
            self.show_scout()
        elif self.screen == "main" and self.scout_seen is not None:
            self.scout_seen = key
            self.show_banner(logic.Status(logic.GREEN, "New scout report is ready. Press 'Scout preview' to see it."))
        else:
            self.scout_seen = key

    def on_online(self) -> None:
        steps = "\n".join(f"{i}.  {s}" for i, s in enumerate(logic.ONLINE_STEPS, 1))
        self.tell("Playing online?", "Mods must be OFF online. Do this first:\n\n" + steps)

    def pick_live_editor(self) -> None:
        folder = filedialog.askdirectory(title="Pick your Live Editor folder")
        if folder:
            self.ledger.paths["live_editor_dir"] = folder
            self.ledger.save()

    def open_folder(self, key: str) -> None:
        folder = self.ledger.resolved_paths().get(key)
        if folder:
            Path(folder).mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                webbrowser.open(Path(folder).as_uri())

    # ---- Mods folder watcher -------------------------------------------
    def poll_mods_folder(self) -> None:
        try:
            if self.ledger is not None and self.open_dialog is None:
                result = logic.watch_mods_folder(self.ledger)
                if result.updated:
                    self.show_banner(logic.Status(logic.GREEN, f"Updated mod spotted: {', '.join(result.updated)}. "
                                                  "It's now set for this game update."))
                fresh = [p for p in result.new_files if str(p) not in self.asked_files]
                if fresh:
                    self.asked_files.update(str(p) for p in fresh)
                    names = ", ".join(p.name for p in fresh)
                    if self.ask_yes_no("New mods found", f"I found new mods in your Mods folder:\n{names}\n\nAdd them?"):
                        self.add_files(fresh)
        except Exception:  # noqa: BLE001 - the watcher must never crash the app
            pass
        try:
            if self.open_dialog is None:
                self.poll_scouting()
        except Exception:  # noqa: BLE001
            pass
        if not self.no_wait:
            self.root.after(5000, self.poll_mods_folder)


def make_root() -> tk.Tk:
    if TkinterDnD is not None:
        try:
            return TkinterDnD.Tk()
        except Exception:  # noqa: BLE001
            pass
    return tk.Tk()


def self_test() -> int:
    """Used by CI on the built exe: every bundled file loads, no window opens."""
    from fcmh import conflicts
    assert conflicts.load_rules()
    assert version_mod.load_tu_table()["fc26"]
    assert "OUTPUT_DIR" in logic.lua_source()
    assert "local OUTPUT_DIR = nil" in logic.lua_source(logic.SCOUT_LUA_NAME)
    from fcmh import scouting
    assert scouting.default_grades()["stars"]
    for name in ("play", "app", "scout"):
        assert resources.files("fcmh.assets").joinpath(f"{name}.png").is_file()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    set_dpi_awareness()
    root = make_root()
    root.geometry("940x780")
    App(root).start()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
