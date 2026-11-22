import os
import sys
import json
import hashlib
import subprocess
import threading
import queue
import shutil
import csv
import tempfile
from pathlib import Path

try:
    import winsound
except ImportError:
    winsound = None
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Mp3 Duplicate Finder"
APP_VERSION = "1.4.0"
AUTHOR = "Konrad Astachow (Kondar)"
COPYRIGHT = "© 2026 Konrad Astachow (Kondar). Wszelkie prawa zastrzeżone."
LICENSE_TEXT = """LICENCJA APLIKACJI
Kod aplikacji Mp3 Duplicate Finder: © 2026 Konrad Astachow (Kondar).
Wszelkie prawa zastrzeżone. Brak zgody na sublicencjonowanie,
modyfikowanie i redystrybucję kodu aplikacji poza uprawnieniami
wynikającymi z bezwzględnie obowiązujących przepisów.

KOMPONENTY ZEWNĘTRZNE
• FFmpeg — GPL-3.0-or-later (konkretna kompilacja Windows essentials
  od Gyan Doshi; warunki i źródła: https://www.gyan.dev/ffmpeg/builds/)
• Chromaprint / fpcalc — LGPL-2.1
  https://github.com/acoustid/chromaprint

FFmpeg i Chromaprint są odrębnymi projektami. Ich licencje dotyczą
odpowiednich komponentów, a nie praw autorskich do kodu tej aplikacji.
Szczegóły dystrybucji komponentów znajdują się w pliku
THIRD_PARTY_NOTICES.txt dołączonym do paczki programu.
"""


def settings_path():
    base = Path(os.environ.get("APPDATA", Path.home()))
    return base / "Mp3DuplicateFinder" / "settings.json"


def bundled_tool(name):
    candidates = []
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / name)
    candidates.append(Path(sys.executable).resolve().parent / name)
    candidates.append(Path(__file__).resolve().parent / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or shutil.which(name + ".exe")


def run_cancellable(cmd, cancel_event, text=False):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=text, encoding="utf-8" if text else None,
                         errors="replace" if text else None,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    while True:
        if cancel_event.is_set():
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
            raise InterruptedError("Skanowanie zatrzymane przez użytkownika.")
        try:
            return p.communicate(timeout=0.25)
        except subprocess.TimeoutExpired:
            continue


def decode_audio(path, ffmpeg, cancel_event):
    cmd = [ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0",
           "-ac", "1", "-ar", "11025", "-f", "s16le", "pipe:1"]
    stdout, stderr = run_cancellable(cmd, cancel_event)
    if not stdout:
        error = stderr.decode("utf-8", "ignore")[-400:]
        raise RuntimeError(error or "Nie można odczytać dźwięku")
    return stdout


def chromaprint_signature(path, fpcalc, cancel_event):
    cmd = [fpcalc, "-raw", "-length", "0", str(path)]
    stdout, stderr = run_cancellable(cmd, cancel_event, text=True)
    if stderr and not stdout:
        raise RuntimeError((stderr or "Błąd fpcalc")[-400:])
    duration, fingerprint = 0.0, None
    for line in stdout.splitlines():
        if line.startswith("DURATION="):
            try:
                duration = float(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("FINGERPRINT="):
            fingerprint = [int(v) for v in line.split("=", 1)[1].strip().split(",") if v.strip()]
    if not fingerprint:
        raise RuntimeError("fpcalc nie zwrócił odcisku audio.")
    return duration, fingerprint


def read_id3_tags(path):
    try:
        from mutagen.mp3 import MP3
        tags = MP3(path).tags or {}
        result = {}
        for key in ("TIT2", "TPE1", "TALB", "TRCK", "TDRC", "TCON"):
            value = tags.get(key)
            if value:
                result[key] = str(value).strip()
        return result
    except Exception:
        return {}


def read_mp3_quality(path):
    try:
        from mutagen.mp3 import MP3
        info = MP3(path).info
        return {"bitrate": int(getattr(info, "bitrate", 0) or 0),
                "sample_rate": int(getattr(info, "sample_rate", 0) or 0),
                "length": float(getattr(info, "length", 0) or 0)}
    except Exception:
        return {"bitrate": 0, "sample_rate": 0, "length": 0.0}


def quality_key(item):
    q = item.get("quality", {})
    return (q.get("bitrate", 0), q.get("sample_rate", 0), item.get("size", 0))


def quality_label(item):
    q = item.get("quality", {})
    bitrate, sample_rate = q.get("bitrate", 0), q.get("sample_rate", 0)
    if bitrate and sample_rate:
        return f"{bitrate // 1000} kb/s · {sample_rate / 1000:.1f} kHz"
    return f"{bitrate // 1000} kb/s" if bitrate else "brak danych"


def comparison_notes(a, b):
    notes = []
    if a.get("size") == b.get("size"):
        notes.append("ten sam rozmiar pliku")
    da, db = a.get("fp", (0, []))[0], b.get("fp", (0, []))[0]
    if da and db and abs(da - db) <= 2:
        notes.append("czas trwania ±2 s")
    tag_labels = (("TIT2", "tytuł"), ("TPE1", "wykonawca"), ("TALB", "album"),
                  ("TRCK", "numer utworu"), ("TDRC", "rok"), ("TCON", "gatunek"))
    for key, label in tag_labels:
        va, vb = a.get("tags", {}).get(key), b.get("tags", {}).get(key)
        if va and vb and va.casefold() == vb.casefold():
            notes.append("ten sam " + label)
    return ", ".join(notes)


def fingerprint_similarity(a, b):
    da, fa = a
    db, fb = b
    if not fa or not fb:
        return 0.0
    if da > 0 and db > 0 and min(da, db) / max(da, db) < 0.72:
        return 0.0
    shorter = min(len(fa), len(fb))
    max_shift = min(8, max(len(fa), len(fb)) - 1)
    best = 0.0
    for shift in range(-max_shift, max_shift + 1):
        start_a, start_b = max(0, shift), max(0, -shift)
        count = min(len(fa) - start_a, len(fb) - start_b)
        if count <= 0 or count < max(8, int(shorter * 0.70)):
            continue
        matching = sum(32 - (fa[start_a + k] ^ fb[start_b + k]).bit_count() for k in range(count))
        best = max(best, matching / (32.0 * count))
    return best


class App:
    PALETTES = {
        "light": {"bg": "#F3F6FA", "surface": "#FFFFFF", "text": "#172033",
                  "muted": "#64748B", "accent": "#2563EB", "accent_hover": "#1D4ED8",
                  "border": "#DCE3EC", "tree": "#FFFFFF", "selected": "#DBEAFE",
                  "success": "#15803D"},
        "dark": {"bg": "#111827", "surface": "#1F2937", "text": "#F3F4F6",
                 "muted": "#A7B0C0", "accent": "#60A5FA", "accent_hover": "#3B82F6",
                 "border": "#374151", "tree": "#182231", "selected": "#263F60",
                 "success": "#4ADE80"}
    }

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1240x800")
        # Minimalny rozmiar chroni stałe sekcje sterujące przed obcięciem.
        self.root.minsize(1160, 700)
        self.events = queue.Queue()
        self.results = []
        self.scanned_items = []
        self.folder = tk.StringVar()
        self.status = tk.StringVar(value="Wybierz folder z muzyką, aby rozpocząć.")
        self.threshold = tk.DoubleVar(value=0.82)
        self.cancel_event = threading.Event()
        self.is_scanning = False
        self.playback_stop_event = threading.Event()
        self.playback_process = None
        self.playback_lock = threading.Lock()
        self.theme_name = self.load_theme()
        self.last_folder = self.load_last_folder()
        if self.last_folder:
            self.folder.set(self.last_folder)
        self._build()
        self.apply_theme()
        self.root.after(100, self._poll)

    def load_theme(self):
        try:
            return json.loads(settings_path().read_text(encoding="utf-8")).get("theme", "light")
        except Exception:
            return "light"

    def load_last_folder(self):
        try:
            return json.loads(settings_path().read_text(encoding="utf-8")).get("last_folder", "")
        except Exception:
            return ""

    def save_settings(self):
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"theme": self.theme_name, "last_folder": self.folder.get().strip()}), encoding="utf-8")
        except Exception:
            pass

    def save_theme(self):
        self.save_settings()

    def _build(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.main = ttk.Frame(self.root, padding=14, style="App.TFrame")
        self.main.grid(row=0, column=0, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, minsize=68, weight=0)
        self.main.grid_rowconfigure(1, minsize=88, weight=0)
        self.main.grid_rowconfigure(2, minsize=112, weight=0)
        self.main.grid_rowconfigure(3, minsize=180, weight=1)
        self.main.grid_rowconfigure(4, minsize=42, weight=0)
        self.main.grid_rowconfigure(5, minsize=30, weight=0)

        header = ttk.Frame(self.main, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        titlebox = ttk.Frame(header, style="App.TFrame")
        titlebox.pack(side="left", fill="x", expand=True)
        ttk.Label(titlebox, text="MP3 DUPLICATE FINDER", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titlebox, text="Wyszukiwanie identycznych i podobnych nagrań na podstawie odcisku audio",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))
        self.theme_btn = ttk.Button(header, text="☾  Tryb ciemny", command=self.toggle_theme, style="Secondary.TButton")
        self.theme_btn.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="O programie", command=self.show_about, style="Secondary.TButton").pack(side="right")

        folder_card = ttk.Frame(self.main, padding=14, style="Card.TFrame")
        folder_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(folder_card, text="FOLDER Z MUZYKĄ", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        folder_row = ttk.Frame(folder_card, style="Card.TFrame")
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.folder, style="App.TEntry", width=62).pack(side="left")
        ttk.Button(folder_row, text="Wybierz folder…", command=self.choose, style="Secondary.TButton").pack(side="left", padx=(8, 0))

        settings_card = ttk.Frame(self.main, padding=14, style="Card.TFrame")
        settings_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(settings_card, text="USTAWIENIA ANALIZY", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        controls = ttk.Frame(settings_card, style="Card.TFrame")
        controls.pack(fill="x")
        ttk.Label(controls, text="Próg podobieństwa:", style="Body.TLabel").pack(side="left")
        self.threshold_scale = ttk.Scale(controls, from_=0.65, to=0.98, variable=self.threshold,
                                         orient="horizontal", length=230)
        self.threshold_scale.pack(side="left", padx=10)
        self.th_label = ttk.Label(controls, text="82%", style="Value.TLabel", width=5)
        self.th_label.pack(side="left")
        self.threshold.trace_add("write", lambda *_: self.th_label.config(text=f"{self.threshold.get():.0%}"))
        self.scan_btn = ttk.Button(controls, text="▶  Rozpocznij skanowanie", command=self.start_scan, style="Primary.TButton", width=24)
        self.scan_btn.pack(side="right")
        self.stop_btn = ttk.Button(controls, text="■  Zatrzymaj", command=self.stop_scan, style="Danger.TButton", width=13, state="disabled")
        self.stop_btn.pack(side="right", padx=(0, 8))
        ttk.Button(controls, text="Eksportuj CSV", command=self.export_csv, style="Secondary.TButton").pack(side="right", padx=(0, 8))
        ttk.Label(settings_card, text="Niższy próg wykrywa więcej podobieństw, ale może zwiększyć liczbę fałszywych trafień.",
                  style="Hint.TLabel").pack(anchor="w", pady=(8, 0))

        results_card = ttk.Frame(self.main, padding=12, style="Card.TFrame")
        results_card.grid(row=3, column=0, sticky="nsew")
        result_header = ttk.Frame(results_card, style="Card.TFrame")
        result_header.pack(fill="x", pady=(0, 8))
        ttk.Label(result_header, text="WYNIKI ANALIZY", style="Section.TLabel").pack(side="left")
        self.count_label = ttk.Label(result_header, text="0 wyników", style="Hint.TLabel")
        self.count_label.pack(side="right")

        table_wrap = ttk.Frame(results_card, style="Card.TFrame")
        table_wrap.pack(fill="both", expand=True)
        cols = ("kind", "similarity", "quality", "size", "path")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="extended")
        for c, title, width in [("kind", "RODZAJ DOPASOWANIA", 280), ("similarity", "ZGODNOŚĆ", 100),
                                ("quality", "JAKOŚĆ MP3", 125), ("size", "ROZMIAR", 100),
                                ("path", "LOKALIZACJA PLIKU", 650)]:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, minwidth=width, stretch=False, anchor="w")
        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(results_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        # Paski przewijania są stale widoczne.
        yscroll.pack(side="right", fill="y")
        xscroll.pack(fill="x")
        self.tree.tag_configure("lower_quality", foreground="#DC2626")
        self.tree.bind("<Double-1>", lambda e: self.open_location())

        footer = ttk.Frame(self.main, style="App.TFrame")
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(footer, text="Otwórz lokalizację", command=self.open_location, style="Secondary.TButton").pack(side="left")
        self.play_btn = ttk.Button(footer, text="▶  Odsłuchaj 15 s", command=self.play_selected, style="Secondary.TButton")
        self.play_btn.pack(side="left", padx=(8, 0))
        self.stop_play_btn = ttk.Button(footer, text="■  Stop audio", command=self.stop_playback, style="Secondary.TButton", state="disabled")
        self.stop_play_btn.pack(side="left", padx=8)
        ttk.Button(footer, text="Przenieś zaznaczone do „Duplikaty”", command=self.move_selected,
                   style="Danger.TButton").pack(side="left")
        statusbar = ttk.Frame(self.main, style="App.TFrame")
        statusbar.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        self.status_label = ttk.Label(statusbar, textvariable=self.status, style="Status.TLabel", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.scan_counts = tk.StringVar(value="Znalezione pliki: 0  |  Przeskanowane: 0/0")
        self.counts_label = ttk.Label(statusbar, textvariable=self.scan_counts, style="Status.TLabel", anchor="e")
        self.counts_label.pack(side="right", padx=(10, 10))
        self.progress = ttk.Progressbar(statusbar, mode="determinate", length=125, maximum=1)
        self.progress.pack(side="right")

    def apply_theme(self):
        p = self.PALETTES[self.theme_name]
        self.root.configure(bg=p["bg"])
        self.style.configure(".", font=("Segoe UI", 10))
        self.style.configure("App.TFrame", background=p["bg"])
        self.style.configure("Card.TFrame", background=p["surface"], borderwidth=1, relief="solid",
                             bordercolor=p["border"])
        self.style.configure("Title.TLabel", background=p["bg"], foreground=p["text"],
                             font=("Segoe UI", 20, "bold"))
        self.style.configure("Subtitle.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        self.style.configure("Section.TLabel", background=p["surface"], foreground=p["muted"],
                             font=("Segoe UI", 9, "bold"))
        self.style.configure("Body.TLabel", background=p["surface"], foreground=p["text"])
        self.style.configure("Value.TLabel", background=p["surface"], foreground=p["accent"],
                             font=("Segoe UI", 11, "bold"))
        self.style.configure("Hint.TLabel", background=p["surface"], foreground=p["muted"], font=("Segoe UI", 8))
        self.style.configure("Status.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        self.style.configure("App.TEntry", fieldbackground=p["tree"], foreground=p["text"],
                             insertcolor=p["text"], bordercolor=p["border"], padding=8)
        self.style.configure("TScale", background=p["surface"], troughcolor=p["border"])
        self.style.configure("TProgressbar", troughcolor=p["border"], background=p["accent"])
        self.style.configure("Treeview", background=p["tree"], fieldbackground=p["tree"],
                             foreground=p["text"], rowheight=30, bordercolor=p["border"],
                             font=("Segoe UI", 9))
        self.style.configure("Treeview.Heading", background=p["surface"], foreground=p["muted"],
                             font=("Segoe UI", 8, "bold"), padding=8, relief="flat")
        self.style.map("Treeview", background=[("selected", p["selected"])],
                       foreground=[("selected", p["text"])])
        self.style.configure("Primary.TButton", background=p["accent"], foreground="#FFFFFF",
                             padding=(14, 9), borderwidth=0, font=("Segoe UI", 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", p["accent_hover"]), ("disabled", p["border"])])
        self.style.configure("Secondary.TButton", background=p["surface"], foreground=p["text"],
                             padding=(10, 8), borderwidth=1, bordercolor=p["border"])
        self.style.map("Secondary.TButton", background=[("active", p["border"])])
        self.style.configure("Danger.TButton", background=p["surface"], foreground="#DC2626",
                             padding=(10, 8), borderwidth=1, bordercolor=p["border"])
        self.style.map("Danger.TButton", background=[("active", p["border"])])
        self.theme_btn.configure(text="☀  Tryb jasny" if self.theme_name == "dark" else "☾  Tryb ciemny")

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.save_theme()
        self.apply_theme()

    def show_about(self):
        win = tk.Toplevel(self.root)
        win.title("O programie i licencja")
        win.transient(self.root)
        win.grab_set()
        win.geometry("590x510")
        win.minsize(500, 420)
        p = self.PALETTES[self.theme_name]
        win.configure(bg=p["bg"])
        frame = ttk.Frame(win, padding=20, style="App.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"Wersja {APP_VERSION}", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 12))
        ttk.Label(frame, text="AUTOR", style="Section.TLabel").pack(anchor="w")
        ttk.Label(frame, text=AUTHOR, style="Body.TLabel", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(4, 12))
        ttk.Label(frame, text="INFORMACJE O LICENCJI", style="Section.TLabel").pack(anchor="w")
        box = tk.Text(frame, wrap="word", height=15, relief="flat", padx=10, pady=10,
                      bg=p["tree"], fg=p["text"], insertbackground=p["text"],
                      font=("Segoe UI", 9), borderwidth=1, highlightthickness=1,
                      highlightbackground=p["border"])
        box.pack(fill="both", expand=True, pady=(6, 12))
        box.insert("1.0", COPYRIGHT + "\n\n" + LICENSE_TEXT)
        box.configure(state="disabled")
        ttk.Button(frame, text="Zamknij", command=win.destroy, style="Primary.TButton").pack(anchor="e")

    def choose(self):
        path = filedialog.askdirectory(title="Wybierz folder z plikami MP3", initialdir=self.folder.get() if Path(self.folder.get()).is_dir() else None)
        if path:
            self.folder.set(path)
            self.save_settings()

    def stop_scan(self):
        if self.is_scanning:
            self.cancel_event.set()
            self.stop_btn.configure(state="disabled")
            self.status.set("Zatrzymywanie skanowania…")

    def start_scan(self):
        folder = self.folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning(APP_TITLE, "Najpierw wybierz prawidłowy folder.")
            return
        ffmpeg = bundled_tool("ffmpeg.exe") or bundled_tool("ffmpeg")
        fpcalc = bundled_tool("fpcalc.exe") or bundled_tool("fpcalc")
        missing = []
        if not ffmpeg:
            missing.append("FFmpeg (ffmpeg.exe)")
        if not fpcalc:
            missing.append("Chromaprint (fpcalc.exe)")
        if missing:
            messagebox.showerror(APP_TITLE, "Nie znaleziono: " + ", ".join(missing) +
                                 ". Umieść pliki obok programu lub sprawdź paczkę instalacyjną.")
            return
        self.save_settings()
        self.cancel_event.clear()
        self.is_scanning = True
        self.scan_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(mode="determinate", maximum=1, value=0)
        self.scan_counts.set("Znalezione pliki: 0  |  Przeskanowane: 0/0")
        self.status.set("Wyszukiwanie plików MP3…")
        self.tree.delete(*self.tree.get_children())
        self.results = []
        self.scanned_items = []
        self.count_label.configure(text="Analiza w toku…")
        threshold = float(self.threshold.get())
        threading.Thread(target=self._scan_worker,
                         args=(Path(folder), ffmpeg, fpcalc, threshold), daemon=True).start()

    def _scan_worker(self, folder, ffmpeg, fpcalc, threshold):
        try:
            files = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".mp3")
            self.events.put(("progress_init", len(files)))
            self.events.put(("status", f"Znaleziono {len(files)} plików MP3. Obliczanie odcisków audio…"))
            items = []
            for i, path in enumerate(files, 1):
                if self.cancel_event.is_set():
                    break
                try:
                    decoded = decode_audio(path, ffmpeg, self.cancel_event)
                    audio_hash = hashlib.sha256(decoded).hexdigest()
                    fingerprint = chromaprint_signature(path, fpcalc, self.cancel_event)
                    items.append({"path": path, "hash": audio_hash, "fp": fingerprint,
                                  "size": path.stat().st_size, "tags": read_id3_tags(path),
                                  "quality": read_mp3_quality(path)})
                except Exception as exc:
                    self.events.put(("status", f"Pominięto {path.name}: {exc}"))
                self.events.put(("progress", "Skanowanie plików", i, len(files)))
            by_hash = {}
            for item in items:
                by_hash.setdefault(item["hash"], []).append(item)
            output = []
            for group in by_hash.values():
                if len(group) > 1:
                    best = max(group, key=quality_key)
                    for item in group:
                        output.append((item, "Identyczna zawartość audio", "100.0%", item is not best))
            total_pairs = len(items) * (len(items) - 1) // 2
            checked = 0
            self.events.put(("compare_init", total_pairs, len(files)))
            for i in range(len(items)):
                if self.cancel_event.is_set():
                    break
                for j in range(i + 1, len(items)):
                    if self.cancel_event.is_set():
                        break
                    a, b = items[i], items[j]
                    checked += 1
                    if a["hash"] != b["hash"]:
                        score = fingerprint_similarity(a["fp"], b["fp"])
                        if score >= threshold:
                            notes = comparison_notes(a, b)
                            suffix = " | " + notes if notes else ""
                            a_is_lower = quality_key(a) < quality_key(b)
                            b_is_lower = quality_key(b) < quality_key(a)
                            output.append((a, f"Podobny utwór ↔ {b['path'].name}{suffix}", f"{score * 100:.1f}%", a_is_lower))
                            output.append((b, f"Podobny utwór ↔ {a['path'].name}{suffix}", f"{score * 100:.1f}%", b_is_lower))
                    if checked % 100 == 0 or checked == total_pairs:
                        self.events.put(("compare_progress", checked, total_pairs, len(files)))
            self.events.put(("done", output, items, len(files), len(items), None, self.cancel_event.is_set()))
        except Exception as exc:
            self.events.put(("done", [], [], 0, 0, str(exc), False))

    def _poll(self):
        try:
            while True:
                msg = self.events.get_nowait()
                if msg[0] == "status":
                    self.status.set(msg[1])
                elif msg[0] == "progress_init":
                    total = msg[1]
                    self.progress.configure(maximum=max(total, 1), value=0)
                    self.scan_counts.set(f"Znalezione pliki: 0  |  Przeskanowane: 0/{total}")
                elif msg[0] == "progress":
                    _, stage, current, total = msg
                    self.progress.configure(mode="determinate", maximum=max(total, 1), value=current)
                    self.scan_counts.set(f"Znalezione pliki: 0  |  Przeskanowane: {current}/{total}")
                    self.status.set(f"{stage}…")
                elif msg[0] == "compare_init":
                    _, total_pairs, scanned = msg
                    self.progress.configure(mode="determinate", maximum=max(total_pairs, 1), value=0)
                    self.scan_counts.set(f"Znalezione pliki: 0  |  Przeskanowane: {scanned}/{scanned}")
                    self.status.set("Porównywanie odcisków audio…")
                elif msg[0] == "compare_progress":
                    _, current, total_pairs, scanned = msg
                    self.progress.configure(maximum=max(total_pairs, 1), value=current)
                    self.scan_counts.set(f"Znalezione pliki: 0  |  Przeskanowane: {scanned}/{scanned}")
                    self.status.set(f"Porównywanie odcisków: {current}/{total_pairs} par")
                elif msg[0] == "playback_done":
                    self.play_btn.configure(state="normal")
                    self.stop_play_btn.configure(state="disabled")
                    self.status.set(msg[1])
                elif msg[0] == "done":
                    _, rows, inventory, total, ok, error, cancelled = msg
                    self.progress.configure(value=0)
                    self.scan_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.is_scanning = False
                    if error:
                        self.count_label.configure(text="Błąd analizy")
                        self.scan_counts.set("Znalezione pliki: 0  |  Przeskanowane: 0/0")
                        self.status.set("Wystąpił błąd podczas analizy.")
                        messagebox.showerror(APP_TITLE, error)
                        continue
                    self.results = rows
                    self.scanned_items = inventory
                    seen = set()
                    duplicate_paths = {str(item["path"]) for item, *_ in rows}
                    for item, kind, score, lower_quality in rows:
                        key = (str(item["path"]), kind, score)
                        if key in seen:
                            continue
                        seen.add(key)
                        self.tree.insert("", "end", values=(kind, score, quality_label(item),
                            f'{item["size"] / 1024 / 1024:.1f} MB', str(item["path"])),
                            tags=("lower_quality",) if lower_quality else ())
                    auto_select = [iid for iid in self.tree.get_children()
                                   if self.tree.item(iid, "values")[4] in duplicate_paths]
                    if auto_select:
                        self.tree.selection_set(auto_select)
                    selected_files = len({self.tree.item(iid, "values")[4] for iid in auto_select})
                    self.count_label.configure(text=f"{len(seen)} wyników · zaznaczono {selected_files} plików z duplikatami")
                    found_files = len({str(item["path"]) for item, _, _, _ in rows})
                    self.scan_counts.set(f"Znalezione pliki: {found_files}  |  Przeskanowane: {ok}/{total}")
                    self.status.set("Skanowanie zatrzymane. Wyświetlono dotychczasowe wyniki." if cancelled else "Zakończono. Sprawdź wyniki przed przenoszeniem.")
                    if not seen and not cancelled:
                        self.status.set("Zakończono. Nie znaleziono dopasowań.")
                    if not cancelled and total > 0:
                        if messagebox.askyesno(APP_TITLE,
                            f"Skanowanie zakończone. Przeskanowano {ok} plików MP3.\\n\\nCzy wygenerować plik CSV z nazwą, lokalizacją, tagami MP3 i bitrate?"):
                            self.export_csv()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def selected_paths(self):
        return list(dict.fromkeys(Path(self.tree.item(i, "values")[4]) for i in self.tree.selection()))

    def play_selected(self):
        if winsound is None:
            messagebox.showerror(APP_TITLE, "Odsłuch próbek jest dostępny w wersji Windows.")
            return
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(APP_TITLE, "Zaznacz plik MP3 na liście wyników.")
            return
        path = paths[0]
        if not path.is_file():
            messagebox.showwarning(APP_TITLE, "Wybrany plik już nie istnieje.")
            return
        ffmpeg = bundled_tool("ffmpeg.exe") or bundled_tool("ffmpeg")
        if not ffmpeg:
            messagebox.showerror(APP_TITLE, "Nie znaleziono FFmpeg.")
            return
        self.stop_playback()
        self.playback_stop_event = threading.Event()
        stop_event = self.playback_stop_event
        self.play_btn.configure(state="disabled")
        self.stop_play_btn.configure(state="normal")
        self.status.set(f"Odtwarzanie próbki (maks. 15 s): {path.name}")
        threading.Thread(target=self._play_worker, args=(path, ffmpeg, stop_event),
                         daemon=True).start()

    def _play_worker(self, path, ffmpeg, stop_event):
        wav_path = None
        message = "Odsłuch zakończony."
        process = None
        try:
            fd, wav_path = tempfile.mkstemp(prefix="mp3df_preview_", suffix=".wav")
            os.close(fd)
            cmd = [ffmpeg, "-y", "-v", "error", "-i", str(path), "-t", "15",
                   "-vn", "-ac", "2", "-ar", "44100", "-sample_fmt", "s16", wav_path]
            process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            with self.playback_lock:
                self.playback_process = process
            while process.poll() is None:
                if stop_event.wait(0.1):
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    message = "Odsłuch zatrzymany."
                    return
            if process.returncode != 0:
                error = process.stderr.read().decode("utf-8", "ignore")[-300:]
                raise RuntimeError(error or "Nie udało się przygotować próbki audio.")
            if not stop_event.is_set():
                winsound.PlaySound(wav_path, winsound.SND_FILENAME)
                if stop_event.is_set():
                    message = "Odsłuch zatrzymany."
        except Exception as exc:
            message = f"Błąd odsłuchu: {exc}"
        finally:
            with self.playback_lock:
                self.playback_process = None
            if wav_path and os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
            self.events.put(("playback_done", message))

    def stop_playback(self):
        self.playback_stop_event.set()
        with self.playback_lock:
            process = self.playback_process
        if process and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        if winsound is not None:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        if hasattr(self, "stop_play_btn"):
            self.stop_play_btn.configure(state="disabled")
            self.play_btn.configure(state="normal")

    def open_location(self):
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(APP_TITLE, "Zaznacz plik na liście wyników.")
            return
        path = paths[0]
        try:
            if sys.platform == "win32":
                os.startfile(path.parent)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path.parent)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def move_selected(self):
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(APP_TITLE, "Zaznacz pliki na liście.")
            return
        if not messagebox.askyesno(APP_TITLE, f"Przenieść {len(paths)} zaznaczonych plików do podfolderu „Duplikaty”?"):
            return
        moved = 0
        for path in paths:
            if not path.exists():
                continue
            dest_dir = path.parent / "Duplikaty"
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / path.name
            n = 1
            while dest.exists():
                dest = dest_dir / f"{path.stem}_{n}{path.suffix}"
                n += 1
            try:
                shutil.move(str(path), str(dest))
                moved += 1
            except Exception as exc:
                messagebox.showwarning(APP_TITLE, f"Nie udało się przenieść {path}: {exc}")
        messagebox.showinfo(APP_TITLE, f"Przeniesiono plików: {moved}.")
        self.status.set(f"Przeniesiono plików: {moved}.")

    def export_csv(self):
        if not self.scanned_items:
            messagebox.showinfo(APP_TITLE, "Brak zeskanowanych plików MP3 do eksportu.")
            return
        dest = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="biblioteka_mp3.csv")
        if not dest:
            return
        tag_names = {
            "TIT2": "Tytuł", "TPE1": "Wykonawca", "TALB": "Album",
            "TRCK": "Numer utworu", "TDRC": "Rok", "TCON": "Gatunek"
        }
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Nazwa", "Lokalizacja", "Tagi MP3", "Bitrate (kb/s)"])
            for item in sorted(self.scanned_items, key=lambda x: str(x["path"]).casefold()):
                path = Path(item["path"])
                tags = item.get("tags", {})
                tag_text = " | ".join(
                    f"{tag_names[key]}: {tags[key]}" for key in tag_names if tags.get(key)
                )
                bitrate = item.get("quality", {}).get("bitrate", 0)
                writer.writerow([path.name, str(path.parent), tag_text,
                    f"{bitrate / 1000:.0f}" if bitrate else ""])
        messagebox.showinfo(APP_TITLE,
            f"Zapisano raport CSV. Liczba plików: {len(self.scanned_items)}.")
