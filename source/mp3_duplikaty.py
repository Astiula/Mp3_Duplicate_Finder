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
import ctypes
from pathlib import Path

try:
    import winsound
except ImportError:
    winsound = None
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Mp3 Duplicate Finder"

def windows_language():
    """Read the language selected in Windows regional settings."""
    try:
        name = ctypes.create_unicode_buffer(85)
        if ctypes.windll.kernel32.GetUserDefaultLocaleName(name, len(name)):
            return name.value.replace("-", "_").split("_", 1)[0].lower()
    except Exception:
        pass
    try:
        import locale
        return (locale.getlocale()[0] or "en").split("_", 1)[0].lower()
    except Exception:
        return "en"


LANGUAGE = "pl" if windows_language() == "pl" else "en"
TRANSLATIONS = {
    "Narzędzia główne": "Home", "Analiza biblioteki": "Library analysis",
    "Biblioteka muzyczna": "Music library", "Folder do przeskanowania": "Folder to scan",
    "Skanowanie": "Scan", "Skanuj": "Scan", "Stop": "Stop", "Raport": "Report",
    "Odsłuch i pliki": "Preview & files", "Odsłuch 15 s": "Preview 15 sec",
    "Otwórz folder": "Open folder", "Zarządzanie": "Manage",
    "Przenieś do Duplikaty": "Move to Duplicates", "Wyniki analizy": "Analysis results",
    "Wyszukiwanie identycznych i podobnych nagrań na podstawie odcisku audio": "Find identical and similar audio tracks using audio fingerprints",
    "O programie": "About", "Tryb ciemny": "Dark mode", "Tryb jasny": "Light mode",
    "FOLDER Z MUZYKĄ": "MUSIC FOLDER", "Wybierz folder…": "Choose folder…",
    "USTAWIENIA ANALIZY": "SCAN SETTINGS", "Próg podobieństwa:": "Similarity threshold:",
    "▶  Rozpocznij skanowanie": "▶  Start scan", "■  Zatrzymaj": "■  Stop",
    "Eksportuj CSV": "Export CSV", "WYNIKI ANALIZY": "SCAN RESULTS",
    "RODZAJ DOPASOWANIA": "MATCH TYPE", "ZGODNOŚĆ": "SIMILARITY",
    "JAKOŚĆ MP3": "MP3 QUALITY", "ROZMIAR": "SIZE", "LOKALIZACJA PLIKU": "FILE LOCATION",
    "Otwórz lokalizację": "Open file location", "▶  Odsłuchaj 15 s": "▶  Play 15 sec",
    "■  Stop audio": "■  Stop audio",
    "Przenieś zaznaczone do „Duplikaty”": "Move selected to “Duplicates”",
    "Zapisz raport CSV": "Save CSV report",
    "Najpierw wybierz prawidłowy folder.": "Please choose a valid folder first.",
    "Brak zeskanowanych plików MP3 do eksportu.": "There are no scanned MP3 files to export.",
    "Wybierz folder z plikami MP3": "Select a folder containing MP3 files",
    "Nazwa": "File name", "Lokalizacja": "Location", "Tagi MP3": "MP3 tags",
    "Duplikat": "Duplicate", "Tytuł": "Title", "Wykonawca": "Artist",
    "Numer utworu": "Track number", "Rok": "Year", "Gatunek": "Genre",
    "TAK — identyczny": "YES — identical", "TAK — podobny": "YES — similar", "Nie": "No",
    "Bitrate (kb/s)": "Bitrate (kb/s)",
    "Skanowanie zatrzymane przez użytkownika.": "Scan stopped by user.",
    "Nie można odczytać dźwięku": "Unable to decode audio",
    "Błąd fpcalc": "fpcalc error",
    "fpcalc nie zwrócił odcisku audio.": "fpcalc did not return an audio fingerprint.",
    "tytuł": "title", "Wyszukiwanie plików MP3…": "Searching for MP3 files…",
    "Skanowanie plików": "Scanning files", "Identyczna zawartość audio": "Identical audio content",
    "Porównywanie odcisków audio…": "Comparing audio fingerprints…",
    "Błąd analizy": "Scan error", "Wystąpił błąd podczas analizy.": "An error occurred during the scan.",
    "Skanowanie zatrzymane. Wyświetlono dotychczasowe wyniki.": "Scan stopped. Results collected so far are displayed.",
    "Zakończono. Sprawdź wyniki przed przenoszeniem.": "Finished. Review the results before moving files.",
    "Zakończono. Nie znaleziono dopasowań.": "Finished. No matches found.",
    "Odsłuch próbek jest dostępny w wersji Windows.": "Audio preview is available in the Windows version.",
    "Zaznacz plik MP3 na liście wyników.": "Select an MP3 file in the results list.",
    "Wybrany plik już nie istnieje.": "The selected file no longer exists.",
    "Odsłuch zakończony.": "Preview finished.", "Odsłuch zatrzymany.": "Preview stopped.",
    "Nie udało się przygotować próbki audio.": "Could not prepare the audio preview.",
    "Zaznacz plik na liście wyników.": "Select a file in the results list.",
    "Zaznacz pliki na liście.": "Select files in the list.",
}


def tr(value):
    return TRANSLATIONS.get(value, value) if LANGUAGE == "en" else value

APP_VERSION = "1.5.3"
UI_DESIGN = "glassy_modern"
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
        self.root.minsize(980, 650)
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
        self.design = UI_DESIGN
        self.theme_name = "dark" if self.design == "dark_pro" else self.load_theme()
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

        # Office-inspired ribbon: fixed command area, expandable results table.
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=0)
        self.root.grid_rowconfigure(3, weight=1)
        self.root.grid_rowconfigure(4, weight=0)
        self.root.grid_columnconfigure(0, weight=1)

        titlebar = ttk.Frame(self.root, style="App.TFrame", padding=(14, 8, 14, 6))
        titlebar.grid(row=0, column=0, sticky="ew")
        titlebar.grid_columnconfigure(0, weight=1)
        design_titles = {"fluent": "FLUENT DESIGN", "classic": "CLASSIC", "dark_pro": "DARK PRO", "dashboard": "DASHBOARD", "explorer": "EXPLORER", "glassy_modern": "GLASSY MODERN"}
        ttk.Label(titlebar, text="MP3 DUPLICATE FINDER  ·  " + design_titles.get(UI_DESIGN, "FLUENT DESIGN"),
                  style="RibbonTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(titlebar, text=f"v{APP_VERSION}", style="RibbonVersion.TLabel").grid(row=0, column=1, padx=(8, 16))
        self.theme_btn = ttk.Button(titlebar, text="🌙  " + tr("Tryb ciemny"),
                                    command=self.toggle_theme, style="RibbonSmall.TButton")
        self.theme_btn.grid(row=0, column=2, padx=(0, 6))
        ttk.Button(titlebar, text=tr("O programie"), command=self.show_about,
                   style="RibbonSmall.TButton").grid(row=0, column=3)

        tabs = ttk.Frame(self.root, style="RibbonTabs.TFrame", padding=(14, 0, 14, 0))
        tabs.grid(row=1, column=0, sticky="ew")
        ttk.Label(tabs, text=tr("Narzędzia główne"), style="RibbonTabActive.TLabel",
                  padding=(0, 5)).pack(side="left")

        ribbon = ttk.Frame(self.root, style="Ribbon.TFrame", padding=(10, 9, 10, 7))
        ribbon.grid(row=2, column=0, sticky="ew")
        ribbon.grid_columnconfigure(0, weight=3)
        ribbon.grid_columnconfigure(1, weight=2)
        ribbon.grid_columnconfigure(2, weight=1)
        ribbon.grid_columnconfigure(3, weight=2)
        ribbon.grid_columnconfigure(4, weight=2)

        # Group 1 — music library.
        library = ttk.Frame(ribbon, style="RibbonGroup.TFrame", padding=(9, 4))
        library.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        ttk.Label(library, text=tr("Biblioteka muzyczna"), style="RibbonGroupTitle.TLabel").pack(anchor="w")
        ttk.Label(library, text=tr("Folder do przeskanowania"), style="RibbonHint.TLabel").pack(anchor="w", pady=(3, 2))
        folder_row = ttk.Frame(library, style="RibbonGroup.TFrame")
        folder_row.pack(fill="x")
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder, style="App.TEntry")
        self.folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="…", width=3, command=self.choose,
                   style="RibbonSmall.TButton").pack(side="left", padx=(5, 0))

        # Group 2 — scan controls.
        scan = ttk.Frame(ribbon, style="RibbonGroup.TFrame", padding=(9, 4))
        scan.grid(row=0, column=1, sticky="nsew", padx=7)
        ttk.Label(scan, text=tr("Skanowanie"), style="RibbonGroupTitle.TLabel").pack(anchor="w")
        threshold_row = ttk.Frame(scan, style="RibbonGroup.TFrame")
        threshold_row.pack(fill="x", pady=(4, 1))
        ttk.Label(threshold_row, text=tr("Próg podobieństwa:"), style="RibbonHint.TLabel").pack(side="left")
        self.th_label = ttk.Label(threshold_row, text="82%", style="RibbonValue.TLabel")
        self.th_label.pack(side="right")
        self.threshold_scale = ttk.Scale(scan, from_=0.65, to=0.98, variable=self.threshold,
                                         orient="horizontal")
        self.threshold_scale.pack(fill="x", pady=(0, 5))
        self.threshold.trace_add("write", lambda *_: self.th_label.config(text=f"{self.threshold.get():.0%}"))
        scan_buttons = ttk.Frame(scan, style="RibbonGroup.TFrame")
        scan_buttons.pack(fill="x")
        self.scan_btn = ttk.Button(scan_buttons, text=tr("▶  Skanuj"), command=self.start_scan,
                                   style="Primary.TButton")
        self.scan_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn = ttk.Button(scan_buttons, text=tr("■  Stop"), command=self.stop_scan,
                                   style="Danger.TButton", state="disabled")
        self.stop_btn.pack(side="left", padx=(5, 0))

        # Group 3 — export.
        export = ttk.Frame(ribbon, style="RibbonGroup.TFrame", padding=(9, 4))
        export.grid(row=0, column=2, sticky="nsew", padx=7)
        ttk.Label(export, text=tr("Raport"), style="RibbonGroupTitle.TLabel").pack(anchor="w")
        ttk.Button(export, text="📄  " + tr("Eksportuj CSV"), command=self.export_csv,
                   style="RibbonSmall.TButton").pack(fill="x", expand=True, pady=(10, 0))

        # Group 4 — preview and navigation.
        audio = ttk.Frame(ribbon, style="RibbonGroup.TFrame", padding=(9, 4))
        audio.grid(row=0, column=3, sticky="nsew", padx=7)
        ttk.Label(audio, text=tr("Odsłuch i pliki"), style="RibbonGroupTitle.TLabel").pack(anchor="w")
        audio_row = ttk.Frame(audio, style="RibbonGroup.TFrame")
        audio_row.pack(fill="x", expand=True, pady=(4, 0))
        self.play_btn = ttk.Button(audio_row, text="🎵  " + tr("Odsłuch 15 s"), command=self.play_selected,
                                   style="RibbonSmall.TButton")
        self.play_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.stop_play_btn = ttk.Button(audio_row, text="⏹  " + tr("Stop audio"), command=self.stop_playback,
                                        style="RibbonSmall.TButton", state="disabled")
        self.stop_play_btn.pack(side="left", fill="x", expand=True, padx=3)
        ttk.Button(audio_row, text="📂  " + tr("Otwórz folder"), command=self.open_location,
                   style="RibbonSmall.TButton").pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Group 5 — file management.
        manage = ttk.Frame(ribbon, style="RibbonGroup.TFrame", padding=(9, 4))
        manage.grid(row=0, column=4, sticky="nsew", padx=(7, 0))
        ttk.Label(manage, text=tr("Zarządzanie"), style="RibbonGroupTitle.TLabel").pack(anchor="w")
        ttk.Button(manage, text="✨  " + tr("Przenieś do Duplikaty"),
                   command=self.move_selected, style="RibbonSmall.TButton").pack(
                       fill="x", expand=True, pady=(10, 0))

        # Short explanatory line under the ribbon.
        hint = ttk.Frame(self.root, style="App.TFrame", padding=(14, 2, 14, 7))
        hint.grid(row=3, column=0, sticky="nsew")
        hint.grid_rowconfigure(2 if UI_DESIGN == "dashboard" else 1, weight=1)
        hint.grid_columnconfigure(0, weight=1)
        results_head = ttk.Frame(hint, style="App.TFrame")
        results_head.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        results_head.grid_columnconfigure(0, weight=1)
        ttk.Label(results_head, text=tr("Wyniki analizy"), style="ResultsTitle.TLabel").grid(
            row=0, column=0, sticky="w")
        self.count_label = ttk.Label(results_head, text="Gotowe do skanowania",
                                     style="ResultsCount.TLabel")
        self.count_label.grid(row=0, column=1, sticky="e")

        if UI_DESIGN == "dashboard":
            metrics = ttk.Frame(hint, style="App.TFrame")
            metrics.grid(row=1, column=0, sticky="ew", pady=(0, 7))
            for col in range(3):
                metrics.grid_columnconfigure(col, weight=1)
            self.dashboard_threshold = tk.StringVar(value="82%")
            self.dashboard_status = tk.StringVar(value="GOTOWY")
            self.dashboard_results = tk.StringVar(value="0")
            self.threshold.trace_add("write", lambda *_: self.dashboard_threshold.set(f"{self.threshold.get():.0%}"))
            for col, (caption, value) in enumerate((
                ("PRÓG PODOBIEŃSTWA", self.dashboard_threshold),
                ("STATUS ANALIZY", self.dashboard_status),
                ("GRUPY DUPLIKATÓW", self.dashboard_results)
            )):
                metric = ttk.Frame(metrics, style="Card.TFrame", padding=(12, 7))
                metric.grid(row=0, column=col, sticky="ew", padx=(0, 5))
                ttk.Label(metric, text=caption, style="RibbonHint.TLabel").pack(anchor="w")
                ttk.Label(metric, textvariable=value, style="Value.TLabel").pack(anchor="w", pady=(2, 0))
        table_wrap = ttk.Frame(hint, style="Card.TFrame", padding=7)
        table_wrap.grid(row=2 if UI_DESIGN == "dashboard" else 1, column=0, sticky="nsew")
        table_wrap.grid_rowconfigure(0, weight=1)
        table_wrap.grid_columnconfigure(0, weight=1)
        cols = ("kind", "similarity", "quality", "size", "path")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="extended")
        for c, title, width in [("kind", "RODZAJ DOPASOWANIA", 260), ("similarity", "ZGODNOŚĆ", 95),
                                ("quality", "JAKOŚĆ MP3", 115), ("size", "ROZMIAR", 90),
                                ("path", "LOKALIZACJA PLIKU", 500)]:
            self.tree.heading(c, text=tr(title))
            self.tree.column(c, width=width, minwidth=70 if c == "path" else width,
                             stretch=(c == "path"), anchor="w")
        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(hint, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=3 if UI_DESIGN == "dashboard" else 2, column=0, sticky="ew", padx=(7, 0))
        self.tree.tag_configure("lower_quality", foreground="#DC2626")
        self.tree.bind("<Double-1>", lambda e: self.open_location())

        statusbar = ttk.Frame(self.root, style="StatusBar.TFrame", padding=(12, 6))
        statusbar.grid(row=4, column=0, sticky="ew")
        statusbar.grid_columnconfigure(0, weight=1)
        self.status_label = ttk.Label(statusbar, textvariable=self.status, style="Status.TLabel", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew")
        self.scan_counts = tk.StringVar(value="Znalezione pliki: 0  |  Przeskanowane: 0/0")
        self.counts_label = ttk.Label(statusbar, textvariable=self.scan_counts, style="Status.TLabel", anchor="e")
        self.counts_label.grid(row=0, column=1, padx=(10, 10))
        self.progress = ttk.Progressbar(statusbar, mode="determinate", length=135, maximum=1)
        self.progress.grid(row=0, column=2)

    def apply_theme(self):
        p = dict(self.PALETTES[self.theme_name])
        design_colors = {
            "fluent": {},
            "classic": {"bg": "#E9EDF2", "surface": "#F8FAFC", "text": "#1F2937", "muted": "#526273", "accent": "#075985", "accent_hover": "#0C4A6E", "border": "#B8C4D1", "tree": "#FFFFFF", "selected": "#D7E7F5"},
            "dark_pro": {"muted": "#91A4BC", "accent": "#0891B2", "accent_hover": "#0E7490", "border": "#26364D"},
            "dashboard": {"bg": "#F4F2FA", "surface": "#FFFFFF", "text": "#24213A", "muted": "#716B87", "accent": "#6D4AFF", "accent_hover": "#5636D9", "border": "#E1DDF0", "tree": "#FFFFFF", "selected": "#E9E3FF"},
            "explorer": {"bg": "#F1F4F6", "surface": "#FFFFFF", "text": "#202B36", "muted": "#657482", "accent": "#0F766E", "accent_hover": "#115E59", "border": "#D5DDE3", "tree": "#FFFFFF", "selected": "#D9F0EC"},
            "glassy_modern": ({"bg": "#EAF4FC", "surface": "#F8FCFF", "text": "#17324D", "muted": "#5D7892", "accent": "#168BDB", "accent_hover": "#0874BD", "border": "#C5DCEF", "tree": "#FFFFFF", "selected": "#D8EEFF", "success": "#0EAD83"} if self.theme_name == "light" else {"bg": "#101F32", "surface": "#1B3048", "text": "#EAF5FF", "muted": "#A5C0D8", "accent": "#45B8F5", "accent_hover": "#2196D2", "border": "#34516D", "tree": "#14263A", "selected": "#244D6D", "success": "#48D6B0"})
        }
        p.update(design_colors.get(self.design, {}))
        self.root.configure(bg=p["bg"])
        base_font = "Arial" if self.design == "classic" else "Segoe UI"
        self.style.configure(".", font=(base_font, 10))
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
        self.style.configure("RibbonTabs.TFrame", background=p["surface"])
        self.style.configure("Ribbon.TFrame", background=p["surface"], relief="solid" if self.design == "glassy_modern" else "flat", borderwidth=1 if self.design == "glassy_modern" else 0)
        self.style.configure("RibbonGroup.TFrame", background=p["surface"] if self.design == "glassy_modern" else p["bg"])
        self.style.configure("ResultsCount.TLabel", background=p["bg"], foreground=p["muted"],
                             font=("Segoe UI", 9))
        self.style.configure("StatusBar.TFrame", background=p["surface"], relief="solid", borderwidth=1)
        self.style.configure("RibbonTitle.TLabel", background=p["bg"], foreground=p["text"],
                             font=("Segoe UI", 15, "bold"))
        self.style.configure("RibbonVersion.TLabel", background=p["bg"], foreground=p["muted"],
                             font=("Segoe UI", 9))
        self.style.configure("RibbonTabActive.TLabel", background=p["surface"], foreground=p["accent"],
                             font=("Segoe UI", 9, "bold"))
        self.style.configure("RibbonTab.TLabel", background=p["surface"], foreground=p["muted"],
                             font=("Segoe UI", 9))
        self.style.configure("RibbonGroupTitle.TLabel", background=p["surface"], foreground=p["muted"],
                             font=("Segoe UI", 8, "bold"))
        self.style.configure("RibbonHint.TLabel", background=p["surface"], foreground=p["muted"],
                             font=("Segoe UI", 8))
        self.style.configure("RibbonValue.TLabel", background=p["surface"], foreground=p["accent"],
                             font=("Segoe UI", 9, "bold"))
        self.style.configure("ResultsTitle.TLabel", background=p["bg"], foreground=p["text"],
                             font=("Segoe UI", 11, "bold"))
        button_pad = (5, 4) if self.design in ("classic", "explorer") else ((12, 9) if self.design == "glassy_modern" else (9, 7))
        self.style.configure("RibbonSmall.TButton", background=p["surface"], foreground=p["text"],
                             padding=button_pad, borderwidth=1, bordercolor=p["border"],
                             font=(base_font, 9))
        self.style.map("RibbonSmall.TButton", background=[("active", p["border"])])
        self.style.configure("RibbonLarge.TButton", background=p["surface"], foreground=p["text"],
                             padding=(5, 6), borderwidth=1, bordercolor=p["border"],
                             font=("Segoe UI", 8))
        self.style.map("RibbonLarge.TButton", background=[("active", p["selected"])])
        self.style.configure("RibbonLargeDanger.TButton", background=p["surface"], foreground="#DC2626",
                             padding=(5, 6), borderwidth=1, bordercolor=p["border"],
                             font=("Segoe UI", 8, "bold"))
        self.style.map("RibbonLargeDanger.TButton", background=[("active", p["border"])])
        self.style.configure("App.TEntry", fieldbackground=p["tree"], foreground=p["text"],
                             insertcolor=p["text"], bordercolor=p["border"], padding=8)
        self.style.configure("TScale", background=p["surface"], troughcolor=p["border"])
        self.style.configure("TProgressbar", troughcolor=p["border"], background=p["accent"])
        row_height = 24 if self.design in ("classic", "explorer") else (34 if self.design == "dashboard" else 30)
        self.style.configure("Treeview", background=p["tree"], fieldbackground=p["tree"],
                             foreground=p["text"], rowheight=row_height, bordercolor=p["border"],
                             font=(base_font, 9))
        heading_pad = 5 if self.design in ("classic", "explorer") else 9
        self.style.configure("Treeview.Heading", background=p["surface"], foreground=p["muted"],
                             font=(base_font, 8, "bold"), padding=heading_pad, relief="flat")
        self.style.map("Treeview", background=[("selected", p["selected"])],
                       foreground=[("selected", p["text"])])
        primary_pad = (10, 6) if self.design in ("classic", "explorer") else (15, 10)
        self.style.configure("Primary.TButton", background=p["accent"], foreground="#FFFFFF",
                             padding=primary_pad, borderwidth=0, font=(base_font, 9, "bold"))
        self.style.map("Primary.TButton", background=[("active", p["accent_hover"]), ("disabled", p["border"])])
        self.style.configure("Secondary.TButton", background=p["surface"], foreground=p["text"],
                             padding=(10, 8), borderwidth=1, bordercolor=p["border"])
        self.style.map("Secondary.TButton", background=[("active", p["border"])])
        self.style.configure("Danger.TButton", background=p["surface"], foreground="#DC2626",
                             padding=(10, 8), borderwidth=1, bordercolor=p["border"])
        self.style.map("Danger.TButton", background=[("active", p["border"])])
        self.theme_btn.configure(text=("☀️  " + tr("Tryb jasny")) if self.theme_name == "dark" else ("🌙  " + tr("Tryb ciemny")))

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
        path = filedialog.askdirectory(title=tr("Wybierz folder z plikami MP3"), initialdir=self.folder.get() if Path(self.folder.get()).is_dir() else None)
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
            messagebox.showwarning(APP_TITLE, tr("Najpierw wybierz prawidłowy folder."))
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
        self.status.set(tr("Wyszukiwanie plików MP3…"))
        self.tree.delete(*self.tree.get_children())
        self.results = []
        self.scanned_items = []
        self.count_label.configure(text="Analiza w toku…")
        if self.design == "dashboard":
            self.dashboard_status.set("SKANOWANIE")
            self.dashboard_results.set("…")
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
                    self.status.set(tr("Porównywanie odcisków audio…"))
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
                        self.count_label.configure(text=tr("Błąd analizy"))
                        self.scan_counts.set("Znalezione pliki: 0  |  Przeskanowane: 0/0")
                        self.status.set(tr("Wystąpił błąd podczas analizy."))
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
                    if self.design == "dashboard":
                        self.dashboard_status.set("ZATRZYMANO" if cancelled else "ZAKOŃCZONO")
                        self.dashboard_results.set(str(len(seen)))
                    found_files = len({str(item["path"]) for item, _, _, _ in rows})
                    self.scan_counts.set(f"Znalezione pliki: {found_files}  |  Przeskanowane: {ok}/{total}")
                    self.status.set(tr("Skanowanie zatrzymane. Wyświetlono dotychczasowe wyniki.") if cancelled else tr("Zakończono. Sprawdź wyniki przed przenoszeniem."))
                    if not seen and not cancelled:
                        self.status.set(tr("Zakończono. Nie znaleziono dopasowań."))
                    if not cancelled and total > 0:
                        if messagebox.askyesno(APP_TITLE,
                            f"Skanowanie zakończone. Przeskanowano {ok} plików MP3.\\n\\nCzy wygenerować plik CSV z nazwą, lokalizacją, tagami MP3 i bitrate?"):
                            self.export_csv()
        except queue.Empty:
            pass
        except Exception as exc:
            # A UI callback error must not permanently stop the event queue.
            try:
                self.status.set(f"Błąd interfejsu: {exc}")
            except Exception:
                pass
        self.root.after(100, self._poll)

    def selected_paths(self):
        return list(dict.fromkeys(Path(self.tree.item(i, "values")[4]) for i in self.tree.selection()))

    def play_selected(self):
        if winsound is None:
            messagebox.showerror(APP_TITLE, tr("Odsłuch próbek jest dostępny w wersji Windows."))
            return
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(APP_TITLE, tr("Zaznacz plik MP3 na liście wyników."))
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
            messagebox.showinfo(APP_TITLE, tr("Zaznacz plik na liście wyników."))
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
            messagebox.showinfo(APP_TITLE, tr("Zaznacz pliki na liście."))
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
            messagebox.showinfo(APP_TITLE, tr("Brak zeskanowanych plików MP3 do eksportu."))
            return
        scan_folder = Path(self.folder.get()).expanduser()
        initial_dir = scan_folder if scan_folder.is_dir() else Path.home()
        dest = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialdir=str(initial_dir),
            initialfile="biblioteka_mp3.csv", title="Zapisz raport CSV")
        if not dest:
            return
        tag_names = {
            "TIT2": tr("Tytuł"), "TPE1": tr("Wykonawca"), "TALB": tr("Album"),
            "TRCK": tr("Numer utworu"), "TDRC": tr("Rok"), "TCON": tr("Gatunek")
        }
        duplicate_types = {}
        for item, kind, score, _lower_quality in self.results:
            key = str(item["path"])
            value = "TAK — identyczny" if kind.startswith("Identyczna zawartość audio") else "TAK — podobny"
            if duplicate_types.get(key) != "TAK — identyczny":
                duplicate_types[key] = value
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([tr("Nazwa"), tr("Lokalizacja"), tr("Tagi MP3"), tr("Bitrate (kb/s)"), tr("Duplikat")])
            for item in sorted(self.scanned_items, key=lambda x: str(x["path"]).casefold()):
                path = Path(item["path"])
                tags = item.get("tags", {})
                tag_text = " | ".join(
                    f"{tag_names[key]}: {tags[key]}" for key in tag_names if tags.get(key)
                )
                bitrate = item.get("quality", {}).get("bitrate", 0)
                duplicate_label = duplicate_types.get(str(path), "Nie")
                writer.writerow([path.name, str(path.parent), tag_text,
                    f"{bitrate / 1000:.0f}" if bitrate else "", duplicate_label])
        messagebox.showinfo(APP_TITLE,
            f"Zapisano raport CSV. Liczba plików: {len(self.scanned_items)}.")

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        error_text = traceback.format_exc()
        try:
            log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Mp3DuplicateFinder"
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / "startup_error.log").write_text(error_text, encoding="utf-8")
        except Exception:
            pass
        try:
            fallback = tk.Tk()
            fallback.withdraw()
            messagebox.showerror(
                APP_TITLE,
                "Nie udało się uruchomić aplikacji. Szczegóły zapisano w pliku:\n"
                + str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Mp3DuplicateFinder" / "startup_error.log")
                + "\n\n" + str(exc)
            )
            fallback.destroy()
        except Exception:
            pass
        raise
