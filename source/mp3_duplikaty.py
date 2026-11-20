import os
import sys
import json
import hashlib
import subprocess
import threading
import queue
import shutil
import csv
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Mp3 Duplicate Finder"
APP_VERSION = "1.1.0"
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


def decode_audio(path, ffmpeg):
    cmd = [ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0",
           "-ac", "1", "-ar", "11025", "-f", "s16le", "pipe:1"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=900, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0 or not p.stdout:
        error = p.stderr.decode("utf-8", "ignore")[-400:]
        raise RuntimeError(error or "Nie można odczytać dźwięku")
    return p.stdout


def chromaprint_signature(path, fpcalc):
    cmd = [fpcalc, "-raw", "-length", "0", str(path)]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding="utf-8", errors="replace", timeout=900,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "Błąd fpcalc")[-400:])
    duration, fingerprint = 0.0, None
    for line in p.stdout.splitlines():
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
        self.root.geometry("1120x740")
        self.root.minsize(880, 600)
        self.events = queue.Queue()
        self.results = []
        self.folder = tk.StringVar()
        self.status = tk.StringVar(value="Wybierz folder z muzyką, aby rozpocząć.")
        self.threshold = tk.DoubleVar(value=0.82)
        self.theme_name = self.load_theme()
        self._build()
        self.apply_theme()
        self.root.after(100, self._poll)

    def load_theme(self):
        try:
            return json.loads(settings_path().read_text(encoding="utf-8")).get("theme", "light")
        except Exception:
            return "light"

    def save_theme(self):
        try:
            path = settings_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"theme": self.theme_name}), encoding="utf-8")
        except Exception:
            pass

    def _build(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.main = ttk.Frame(self.root, padding=20, style="App.TFrame")
        self.main.pack(fill="both", expand=True)

        header = ttk.Frame(self.main, style="App.TFrame")
        header.pack(fill="x", pady=(0, 16))
        titlebox = ttk.Frame(header, style="App.TFrame")
        titlebox.pack(side="left", fill="x", expand=True)
        ttk.Label(titlebox, text="MP3 DUPLICATE FINDER", style="Title.TLabel").pack(anchor="w")
        ttk.Label(titlebox, text="Wyszukiwanie identycznych i podobnych nagrań na podstawie odcisku audio",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(4, 0))
        self.theme_btn = ttk.Button(header, text="☾  Tryb ciemny", command=self.toggle_theme, style="Secondary.TButton")
        self.theme_btn.pack(side="right", padx=(8, 0))
        ttk.Button(header, text="O programie", command=self.show_about, style="Secondary.TButton").pack(side="right")

        folder_card = ttk.Frame(self.main, padding=14, style="Card.TFrame")
        folder_card.pack(fill="x", pady=(0, 12))
        ttk.Label(folder_card, text="FOLDER Z MUZYKĄ", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        folder_row = ttk.Frame(folder_card, style="Card.TFrame")
        folder_row.pack(fill="x")
        ttk.Entry(folder_row, textvariable=self.folder, style="App.TEntry").pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Wybierz folder…", command=self.choose, style="Secondary.TButton").pack(side="left", padx=(8, 0))

        settings_card = ttk.Frame(self.main, padding=14, style="Card.TFrame")
        settings_card.pack(fill="x", pady=(0, 12))
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
        self.scan_btn = ttk.Button(controls, text="▶  Rozpocznij skanowanie", command=self.start_scan, style="Primary.TButton")
        self.scan_btn.pack(side="right")
        ttk.Button(controls, text="Eksportuj CSV", command=self.export_csv, style="Secondary.TButton").pack(side="right", padx=(0, 8))
        ttk.Label(settings_card, text="Niższy próg wykrywa więcej podobieństw, ale może zwiększyć liczbę fałszywych trafień.",
                  style="Hint.TLabel").pack(anchor="w", pady=(8, 0))

        results_card = ttk.Frame(self.main, padding=12, style="Card.TFrame")
        results_card.pack(fill="both", expand=True)
        result_header = ttk.Frame(results_card, style="Card.TFrame")
        result_header.pack(fill="x", pady=(0, 8))
        ttk.Label(result_header, text="WYNIKI ANALIZY", style="Section.TLabel").pack(side="left")
        self.count_label = ttk.Label(result_header, text="0 wyników", style="Hint.TLabel")
        self.count_label.pack(side="right")

        table_wrap = ttk.Frame(results_card, style="Card.TFrame")
        table_wrap.pack(fill="both", expand=True)
        cols = ("kind", "similarity", "size", "path")
        self.tree = ttk.Treeview(table_wrap, columns=cols, show="headings", selectmode="extended")
        for c, title, width in [("kind", "RODZAJ DOPASOWANIA", 250), ("similarity", "ZGODNOŚĆ", 100),
                                ("size", "ROZMIAR", 100), ("path", "LOKALIZACJA PLIKU", 570)]:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor="w")
        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(results_card, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(fill="x")
        self.tree.bind("<Double-1>", lambda e: self.open_location())

        footer = ttk.Frame(self.main, style="App.TFrame")
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Otwórz lokalizację", command=self.open_location, style="Secondary.TButton").pack(side="left")
        ttk.Button(footer, text="Przenieś zaznaczone do „Duplikaty”", command=self.move_selected,
                   style="Danger.TButton").pack(side="left", padx=8)
        statusbar = ttk.Frame(self.main, style="App.TFrame")
        statusbar.pack(fill="x", pady=(10, 0))
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
        path = filedialog.askdirectory(title="Wybierz folder z plikami MP3")
        if path:
            self.folder.set(path)

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
        self.scan_btn.configure(state="disabled")
        self.progress.configure(mode="determinate", maximum=1, value=0)
        self.scan_counts.set("Znalezione pliki: 0  |  Przeskanowane: 0/0")
        self.status.set("Wyszukiwanie plików MP3…")
        self.tree.delete(*self.tree.get_children())
        self.results = []
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
                try:
                    decoded = decode_audio(path, ffmpeg)
                    audio_hash = hashlib.sha256(decoded).hexdigest()
                    fingerprint = chromaprint_signature(path, fpcalc)
                    items.append({"path": path, "hash": audio_hash, "fp": fingerprint,
                                  "size": path.stat().st_size})
                except Exception as exc:
                    self.events.put(("status", f"Pominięto {path.name}: {exc}"))
                self.events.put(("progress", "Skanowanie plików", i, len(files)))
            by_hash = {}
            for item in items:
                by_hash.setdefault(item["hash"], []).append(item)
            output = []
            for group in by_hash.values():
                if len(group) > 1:
                    for item in group:
                        output.append((item, "Identyczna zawartość audio", "100.0%"))
            total_pairs = len(items) * (len(items) - 1) // 2
            checked = 0
            self.events.put(("compare_init", total_pairs, len(files)))
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    a, b = items[i], items[j]
                    if a["hash"] == b["hash"]:
                        continue
                    score = fingerprint_similarity(a["fp"], b["fp"])
                    if score >= threshold:
                        output.append((a, f"Podobny utwór ↔ {b['path'].name}", f"{score * 100:.1f}%"))
                        output.append((b, f"Podobny utwór ↔ {a['path'].name}", f"{score * 100:.1f}%"))
                    checked += 1
                    if checked % 100 == 0 or checked == total_pairs:
                        self.events.put(("compare_progress", checked, total_pairs, len(files)))
            self.events.put(("done", output, len(files), len(items), None))
        except Exception as exc:
            self.events.put(("done", [], 0, 0, str(exc)))

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
                elif msg[0] == "done":
                    _, rows, total, ok, error = msg
                    self.progress.configure(value=0)
                    self.scan_btn.configure(state="normal")
                    if error:
                        self.count_label.configure(text="Błąd analizy")
                        self.scan_counts.set("Znalezione pliki: 0  |  Przeskanowane: 0/0")
                        self.status.set("Wystąpił błąd podczas analizy.")
                        messagebox.showerror(APP_TITLE, error)
                        continue
                    self.results = rows
                    seen = set()
                    for item, kind, score in rows:
                        key = (str(item["path"]), kind, score)
                        if key in seen:
                            continue
                        seen.add(key)
                        self.tree.insert("", "end", values=(kind, score,
                            f'{item["size"] / 1024 / 1024:.1f} MB', str(item["path"])))
                    self.count_label.configure(text=f"{len(seen)} wyników")
                    found_files = len({str(item["path"]) for item, _, _ in rows})
                    self.scan_counts.set(f"Znalezione pliki: {found_files}  |  Przeskanowane: {ok}/{total}")
                    self.status.set("Zakończono. Sprawdź wyniki przed przenoszeniem.")
                    if not seen:
                        self.status.set("Zakończono. Nie znaleziono dopasowań.")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def selected_paths(self):
        return [Path(self.tree.item(i, "values")[3]) for i in self.tree.selection()]

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
        if not self.tree.get_children():
            messagebox.showinfo(APP_TITLE, "Brak wyników do eksportu.")
            return
        dest = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], initialfile="duplikaty_mp3.csv")
        if not dest:
            return
        with open(dest, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Rodzaj dopasowania", "Zgodność fingerprintu", "Rozmiar", "Plik"])
            for item_id in self.tree.get_children():
                writer.writerow(self.tree.item(item_id, "values"))
        messagebox.showinfo(APP_TITLE, "Zapisano raport CSV.")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
