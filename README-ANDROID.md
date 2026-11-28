# MP3 Duplicate Finder — Android (Glassy Modern)

Niezależny projekt Android w gałęzi `android-app`. Aplikacja Windows pozostaje bez zmian.

## Budowanie
Projekt można otworzyć w Android Studio jako projekt Gradle. CI buduje APK poleceniem `gradle :app:assembleDebug`.

Artefakt: `app/build/outputs/apk/debug/app-debug.apk`.

## Zaimplementowany etap
- Kotlin + Jetpack Compose, interfejs Glassy Modern.
- Wybór folderu przez Android Storage Access Framework i zapamiętanie uprawnień.
- Rekurencyjne skanowanie MP3.
- Odczyt podstawowych tagów przez MediaMetadataRetriever.
- SHA-256 i wykrywanie plików identycznych bajt po bajcie.
- Wybór jednego oryginału według bitrate, rozmiaru i ścieżki.
- Lista wszystkich plików, także bez duplikatów.
- Wyszukiwanie, zaznaczanie sugerowanych kopii, motyw jasny/ciemny.
- Eksport CSV przez systemowy selektor miejsca zapisu.
- Pole klucza AcoustID zapisywane lokalnie w prywatnych preferencjach; klucz nie jest osadzony w APK.

## Różnice względem Windows 1.5.12
To jest pierwszy działający etap Androida, a nie pełny odpowiednik Windows. SHA-256 wykrywa tylko identyczne pliki, nie wykrywa utworów ponownie zakodowanych ani podobieństwa akustycznego.

Do pełnej zgodności należy jeszcze zbudować i dołączyć Chromaprint dla ABI Androida oraz dodać:
- fingerprint similarity i rozpoznawanie AcoustID,
- MusicBrainz i uzupełnianie tagów/okładek,
- import CSV i odtwarzanie podglądu,
- bezpieczne przenoszenie/usuwanie plików,
- trwały cache wyników skanowania.
