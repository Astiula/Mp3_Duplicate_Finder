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

APP_TITLE = 'MP3 Duplikaty'


def bundled_tool(name):
    """Find a bundled executable (PyInstaller) or one beside the script."""
    candidates = []
    if getattr(sys, '_MEIPASS', None):
        candidates.append(Path(sys._MEIPASS) / name)
    candidates.append(Path(sys.executable).resolve().parent / name)
    candidates.append(Path(__file__).resolve().parent / name)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or shutil.which(name + '.exe')


def decode_audio(path, ffmpeg):
    cmd = [ffmpeg, '-v', 'error', '-i', str(path), '-map', '0:a:0',
           '-ac', '1', '-ar', '11025', '-f', 's16le', 'pipe:1']
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode != 0 or not p.stdout:
        error = p.stderr.decode('utf-8', 'ignore')[-400:]
        raise RuntimeError(error or 'Nie można odczytać dźwięku')
    return p.stdout


def chromaprint_signature(path, fpcalc):
    """Return Chromaprint's sequence of 32-bit audio-fingerprint words."""
    cmd = [fpcalc, '-raw', '-length', '0', str(path)]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, encoding='utf-8', errors='replace', timeout=900,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or 'Błąd fpcalc')[-400:])
    duration = None
    fingerprint = None
    for line in p.stdout.splitlines():
        if line.startswith('DURATION='):
            try:
                duration = float(line.split('=', 1)[1])
            except ValueError:
                pass
        elif line.startswith('FINGERPRINT='):
            value = line.split('=', 1)[1].strip()
            fingerprint = [int(v) for v in value.split(',') if v.strip()]
    if not fingerprint:
        raise RuntimeError('fpcalc nie zwrócił odcisku audio. Sprawdź plik i wersję Chromaprint.')
    return duration or 0.0, fingerprint


def fingerprint_similarity(a, b):
    """Compare fingerprints with frame shifts; supports small leading/trailing edits."""
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
        start_a = max(0, shift)
        start_b = max(0, -shift)
        count = min(len(fa) - start_a, len(fb) - start_b)
        if count <= 0 or count < max(8, int(shorter * 0.70)):
            continue
        matching = 0
        for k in range(count):
            matching += 32 - (fa[start_a + k] ^ fb[start_b + k]).bit_count()
        score = matching / (32.0 * count)
        if score > best:
            best = score
    return best


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry('1050x680')
        root.minsize(820, 520)
        self.events = queue.Queue()
        self.results = []
        self.folder = tk.StringVar()
        self.status = tk.StringVar(value='Wybierz folder z muzyką MP3.')
        self.threshold = tk.DoubleVar(value=0.82)
        self._build()
        root.after(100, self._poll)

    def _build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill='x')
        ttk.Label(top, text='Folder z muzyką:').pack(side='left')
        ttk.Entry(top, textvariable=self.folder).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(top, text='Wybierz…', command=self.choose).pack(side='left')

        opts = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        opts.pack(fill='x')
        ttk.Label(opts, text='Próg zgodności fingerprintu:').pack(side='left')
        ttk.Scale(opts, from_=0.65, to=0.98, variable=self.threshold,
                  orient='horizontal', length=220).pack(side='left', padx=8)
        self.th_label = ttk.Label(opts, text='0.82')
        self.th_label.pack(side='left')
        self.threshold.trace_add('write', lambda *_: self.th_label.config(text=f'{self.threshold.get():.2f}'))
        self.scan_btn = ttk.Button(opts, text='Skanuj MP3', command=self.start_scan)
        self.scan_btn.pack(side='left', padx=18)
        ttk.Button(opts, text='Eksportuj CSV', command=self.export_csv).pack(side='left')

        cols = ('kind', 'similarity', 'size', 'path')
        self.tree = ttk.Treeview(self.root, columns=cols, show='headings', selectmode='extended')
        for c, title, width in [('kind', 'Typ wyniku', 245), ('similarity', 'Zgodność', 100),
                                ('size', 'Rozmiar', 100), ('path', 'Plik', 590)]:
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor='w')
        self.tree.pack(fill='both', expand=True, padx=10, pady=5)

        bar = ttk.Frame(self.root, padding=10)
        bar.pack(fill='x')
        ttk.Button(bar, text='Otwórz lokalizację pliku', command=self.open_location).pack(side='left')
        ttk.Button(bar, text='Przenieś zaznaczone do folderu „Duplikaty”',
                   command=self.move_selected).pack(side='left', padx=8)
        ttk.Label(self.root, textvariable=self.status, relief='sunken', anchor='w', padding=6).pack(fill='x', side='bottom')
        self.tree.bind('<Double-1>', lambda e: self.open_location())

    def choose(self):
        p = filedialog.askdirectory(title='Wybierz folder z plikami MP3')
        if p:
            self.folder.set(p)

    def start_scan(self):
        folder = self.folder.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning(APP_TITLE, 'Najpierw wybierz prawidłowy folder.')
            return
        ffmpeg = bundled_tool('ffmpeg.exe') or bundled_tool('ffmpeg')
        fpcalc = bundled_tool('fpcalc.exe') or bundled_tool('fpcalc')
        missing = []
        if not ffmpeg:
            missing.append('FFmpeg (ffmpeg.exe)')
        if not fpcalc:
            missing.append('Chromaprint (fpcalc.exe)')
        if missing:
            messagebox.showerror(APP_TITLE,
                'Nie znaleziono wymaganych programów: ' + ', '.join(missing) +
                '. Umieść oba pliki EXE obok programu lub dodaj je do PATH. Zobacz README.txt.')
            return
        self.scan_btn.config(state='disabled')
        self.tree.delete(*self.tree.get_children())
        self.results = []
        threshold = float(self.threshold.get())
        threading.Thread(target=self._scan_worker, args=(Path(folder), ffmpeg, fpcalc, threshold), daemon=True).start()

    def _scan_worker(self, folder, ffmpeg, fpcalc, threshold):
        files = sorted(p for p in folder.rglob('*') if p.is_file() and p.suffix.lower() == '.mp3')
        self.events.put(('status', f'Znaleziono {len(files)} plików MP3. Obliczanie fingerprintów…'))
        items = []
        for i, path in enumerate(files, 1):
            try:
                decoded = decode_audio(path, ffmpeg)
                audio_hash = hashlib.sha256(decoded).hexdigest()
                fingerprint = chromaprint_signature(path, fpcalc)
                items.append({'path': path, 'hash': audio_hash, 'fp': fingerprint,
                              'size': path.stat().st_size})
            except Exception as exc:
                self.events.put(('status', f'Pominięto {path.name}: {exc}'))
            if i % 3 == 0 or i == len(files):
                self.events.put(('status', f'Analiza fingerprintów: {i}/{len(files)}'))

        by_hash = {}
        for item in items:
            by_hash.setdefault(item['hash'], []).append(item)
        output = []
        for group in by_hash.values():
            if len(group) > 1:
                for item in group:
                    output.append((item, 'Identyczna zawartość audio', '100.0%'))

        total_pairs = len(items) * (len(items) - 1) // 2
        checked = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                if a['hash'] == b['hash']:
                    continue
                score = fingerprint_similarity(a['fp'], b['fp'])
                if score >= threshold:
                    output.append((a, f'Podobny utwór ↔ {b["path"].name}', f'{score * 100:.1f}%'))
                    output.append((b, f'Podobny utwór ↔ {a["path"].name}', f'{score * 100:.1f}%'))
                checked += 1
                if checked % 100 == 0:
                    self.events.put(('status', f'Porównywanie odcisków: {checked}/{total_pairs} par'))
        self.events.put(('done', output, len(files), len(items)))

    def _poll(self):
        try:
            while True:
                msg = self.events.get_nowait()
                if msg[0] == 'status':
                    self.status.set(msg[1])
                elif msg[0] == 'done':
                    _, rows, total, ok = msg
                    self.results = rows
                    seen = set()
                    for item, kind, score in rows:
                        key = (str(item['path']), kind, score)
                        if key in seen:
                            continue
                        seen.add(key)
                        self.tree.insert('', 'end', values=(kind, score,
                            f'{item["size"] / 1024 / 1024:.1f} MB', str(item['path'])))
                    self.status.set(f'Gotowe. Plików: {total}, przeanalizowano: {ok}, wpisy wyników: {len(seen)}. Zweryfikuj wyniki przed przeniesieniem.')
                    self.scan_btn.config(state='normal')
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def selected_paths(self):
        return [Path(self.tree.item(i, 'values')[3]) for i in self.tree.selection()]

    def open_location(self):
        paths = self.selected_paths()
        if not paths:
            return
        path = paths[0]
        try:
            if sys.platform == 'win32':
                os.startfile(path.parent)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(path.parent)])
            else:
                subprocess.Popen(['xdg-open', str(path.parent)])
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def move_selected(self):
        paths = self.selected_paths()
        if not paths:
            messagebox.showinfo(APP_TITLE, 'Zaznacz pliki na liście.')
            return
        if not messagebox.askyesno(APP_TITLE, f'Przenieść {len(paths)} zaznaczonych plików do podfolderu „Duplikaty”?'):
            return
        moved = 0
        for path in paths:
            if not path.exists():
                continue
            dest_dir = path.parent / 'Duplikaty'
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / path.name
            n = 1
            while dest.exists():
                dest = dest_dir / f'{path.stem}_{n}{path.suffix}'
                n += 1
            try:
                shutil.move(str(path), str(dest))
                moved += 1
            except Exception as exc:
                messagebox.showwarning(APP_TITLE, f'Nie udało się przenieść {path}: {exc}')
        messagebox.showinfo(APP_TITLE, f'Przeniesiono plików: {moved}.')
        self.status.set(f'Przeniesiono plików: {moved}.')

    def export_csv(self):
        if not self.tree.get_children():
            messagebox.showinfo(APP_TITLE, 'Brak wyników do eksportu.')
            return
        dest = filedialog.asksaveasfilename(defaultextension='.csv',
            filetypes=[('CSV', '*.csv')], initialfile='duplikaty_mp3.csv')
        if not dest:
            return
        with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['Typ wyniku', 'Zgodność fingerprintu', 'Rozmiar', 'Plik'])
            for item_id in self.tree.get_children():
                writer.writerow(self.tree.item(item_id, 'values'))
        messagebox.showinfo(APP_TITLE, 'Zapisano raport CSV.')


if __name__ == '__main__':
    root = tk.Tk()
    App(root)
    root.mainloop()
