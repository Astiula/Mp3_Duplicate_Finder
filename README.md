# Mp3 Duplicate Finder

Aplikacja desktopowa dla Windows 10/11 do wyszukiwania identycznych plików MP3 oraz podobnych nagrań po ponownym kodowaniu, z wykorzystaniem Chromaprint/audio fingerprint.

## Kompilacja

Repozytorium zawiera kod źródłowy i workflow GitHub Actions budujący jednoplikowy program Windows x64. Workflow pobiera FFmpeg i Chromaprint z ich kanałów dystrybucji, weryfikuje sumę SHA-256 Chromaprint, a następnie dołącza oba programy do EXE przez PyInstaller.

Gotowy plik jest publikowany jako artefakt GitHub Actions: **Mp3_Duplicate_Finder-Windows-x64**.

## Autorstwo

Autorstwo projektu i kodu aplikacji: **Konrad Astachow (Kondar)** — zgodnie z deklaracją autora.

## Komponenty zewnętrzne

- FFmpeg: https://ffmpeg.org/ — build Windows essentials od Gyan Doshi; build essentials jest dystrybuowany na licencji GPLv3. Zob. https://www.gyan.dev/ffmpeg/builds/
- Chromaprint / fpcalc: https://github.com/acoustid/chromaprint — LGPL-2.1-or-later.

Repozytorium nie zawiera licencji open-source udzielającej dodatkowych praw do kodu aplikacji. Brak pliku LICENSE oznacza, że nie udzielono ogólnej licencji na ponowne wykorzystanie kodu.
