# Mp3 Duplicate Finder

Program desktopowy Windows 10/11 x64 do wyszukiwania identycznych plików MP3 oraz podobnych nagrań po ponownym kodowaniu, na podstawie audio fingerprint (Chromaprint).

## Interfejs
- odświeżony układ z oddzielnymi sekcjami folderu, ustawień i wyników;
- jasny i ciemny motyw, z zapamiętaniem wybranego trybu;
- okno „O programie” z informacją o autorze i komponentach zewnętrznych;
- pasek postępu, licznik wyników, przewijanie tabeli;
- eksport CSV i ręczne przenoszenie zaznaczonych plików.

## Autorstwo i licencja aplikacji
Autor aplikacji i kodu źródłowego: **Konrad Astachow (Kondar)**, zgodnie z deklaracją autora.

Kod aplikacji jest udostępniany na zasadach własnościowych (all rights reserved). Repozytorium nie udziela licencji open-source na kod aplikacji. Nie oznacza to przejęcia praw do komponentów zewnętrznych.

## Komponenty zewnętrzne dołączane do kompilacji
- **FFmpeg** — Windows essentials build od Gyan Doshi; buildy essentials są oznaczone jako GPLv3. Informacje o licencji, źródłach i kompilacjach: https://www.gyan.dev/ffmpeg/builds/ oraz https://ffmpeg.org/legal.html.
- **Chromaprint / fpcalc 1.6.1** — LGPL 2.1; kod Chromaprint zawiera również części na licencji MIT. Szczegóły: https://github.com/acoustid/chromaprint/blob/v1.6.1/LICENSE.md.

Paczka dystrybucyjna zawiera osobny plik THIRD_PARTY_NOTICES.txt i dostępne informacje licencyjne komponentów. FFmpeg i Chromaprint pozostają odrębnymi projektami i zachowują własne licencje. To jest informacja o komponentach, a nie porada prawna.


## Bezpieczeństwo i dystrybucja Windows
- Kompilacja Windows używa trybu PyInstaller `onedir`, bez UPX i bez samorozpakowującego się pliku `onefile`; to ogranicza część heurystycznych fałszywych alarmów, ale nie gwarantuje braku detekcji.
- Paczka zawiera `SHA256SUMS.txt` do weryfikacji integralności oraz informacje o komponentach zewnętrznych.
- Program nie instaluje usług, sterowników, zadań harmonogramu ani wpisów autostartu.
- Program analizuje pliki w folderze wybranym przez użytkownika. Przenoszenie plików wymaga osobnej akcji użytkownika.
- Podpis Authenticode może być dodany w procesie CI po skonfigurowaniu sekretów repozytorium `WINDOWS_SIGNING_CERT_BASE64` i `WINDOWS_SIGNING_CERT_PASSWORD`. Bez certyfikatu build pozostaje niepodpisany i SmartScreen może wyświetlać ostrzeżenie z powodu braku reputacji wydawcy.
- Nie ma technicznej możliwości zagwarantowania wyniku identycznego dla wszystkich antywirusów. W razie detekcji należy przesłać konkretny plik i nazwę wykrycia do analizy, a nie wyłączać ochronę systemu.
